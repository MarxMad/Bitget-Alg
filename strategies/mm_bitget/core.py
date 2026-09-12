"""
Market maker quote logic — pure functions, no I/O.

Quote width is 2.5x the asset's own rolling 1m volatility, not a fixed
percentage. That distinction is the whole strategy: the previous bot quoted a
constant mid±0.02%, which on BTC's 0.0001%-wide book rests far outside the touch
and only fills when price runs through it. That is buying dips and selling rips
— mean reversion with negative expectancy — not spread capture.

Measured over 56 asset-days of Bitget 1m data (SOL, ETH, BTC, XLM):

    width   PnL/day   days up   volume/day
    2.0x    -$0.31      34%       $2,713     loses
    2.5x    +$0.02      52%       $1,652     breakeven, max volume  <-- default
    3.0x    +$0.28      62%       $1,034     profitable, less volume

2.5x is the widest-volume point whose P&L is statistically zero
(+$0.02 +/- $0.17 standard error). Tighter loses to adverse selection; wider
earns more but generates less of what this bot exists to generate.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class MMConfig:
    symbols: List[str] = field(default_factory=lambda: ["SOLUSDT", "BTCUSDT"])

    # Quote half-width as a multiple of rolling 1m volatility. See module docstring.
    vol_multiple: float = 2.5

    # Bars of 1m history used for the volatility estimate.
    vol_window: int = 60

    # Notional per quote, USDT. Ignored while auto_size is on — size_from_equity
    # recomputes it from live equity every cycle, so the book grows with the
    # account instead of needing a redeploy.
    order_usdt: float = 5.0

    # Resize from live equity each cycle.
    auto_size: bool = True

    # Daily P&L standard deviation the sizer is allowed to target, as a fraction
    # of equity. 3% is the default; below ~$30 of equity no size satisfies it and
    # the bot declines to trade rather than quietly taking more risk.
    risk_budget: float = 0.03

    # Symbols the sizer may spread across, most liquid first.
    universe: List[str] = field(default_factory=lambda: [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
        "ADAUSDT", "LINKUSDT", "XLMUSDT", "SUIUSDT", "NEARUSDT"])

    # Stop quoting the side that would grow inventory past this many orders.
    max_inventory_orders: int = 10

    # Shift both quotes against inventory. MEASURED HARMFUL and off by default:
    # over 56 asset-days, 0.0 returns +$7.13 where 0.5 returns -$18.88 and 1.0
    # returns -$24.35. Skewing to flatten means selling cheaper to get out, which
    # in a trend means selling into it repeatedly. The hard inventory cap already
    # bounds the risk without paying a spread for it.
    inventory_skew: float = 0.0

    # Seconds between requotes. Faster is not better: cancel/replace storms with
    # no intent to fill are what surveillance flags as layering.
    requote_seconds: float = 15.0

    # Reprice only when the quote has drifted this far, so a quiet book is left alone.
    reprice_threshold: float = 0.25

    # Halt for the day past this loss, as a fraction of starting equity.
    daily_loss_limit: float = 0.10

    # Cap total notional across all symbols at this multiple of equity.
    max_gross_leverage: float = 5.0

    paper: bool = True


def realized_vol(closes: List[float], window: int) -> Optional[float]:
    """Mean absolute 1-bar return over the window — robust to the fat tails
    that make a standard deviation jumpy on crypto minute bars."""
    if len(closes) < window + 1:
        return None
    moves = [abs(closes[i] / closes[i - 1] - 1)
             for i in range(len(closes) - window, len(closes))
             if closes[i - 1] > 0]
    if not moves:
        return None
    v = sum(moves) / len(moves)
    return v if v > 0 else None


def quote_prices(mid: float, vol: float, inventory_usd: float,
                 cfg: MMConfig) -> Optional[Tuple[float, float]]:
    """
    (bid, ask) around mid. Returns None when the pair would cross — quoting a
    bid above your own ask is a self-match waiting to happen, and the fix is to
    not send it rather than to rely on the exchange rejecting it.
    """
    half = mid * vol * cfg.vol_multiple
    cap = cfg.max_inventory_orders * cfg.order_usdt
    skew = (inventory_usd / cap) * half * cfg.inventory_skew if cap else 0.0

    bid, ask = mid - half - skew, mid + half - skew
    if bid <= 0 or bid >= ask:
        return None
    return bid, ask


def sides_allowed(inventory_usd: float, cfg: MMConfig) -> Tuple[bool, bool]:
    """(may_bid, may_ask) — stop growing an inventory already at its cap."""
    cap = cfg.max_inventory_orders * cfg.order_usdt
    return inventory_usd < cap, inventory_usd > -cap


def needs_reprice(old: Optional[Tuple[float, float]],
                  new: Tuple[float, float], vol: float, mid: float,
                  cfg: MMConfig) -> bool:
    """Requote only on real drift. Constant cancel/replace against a still book
    is the pattern surveillance reads as layering, and it buys nothing."""
    if old is None:
        return True
    tol = mid * vol * cfg.reprice_threshold
    return abs(new[0] - old[0]) > tol or abs(new[1] - old[1]) > tol


# ─── Auto-sizing from live equity ─────────────────────────────────────────────
#
# Measured on 15 days of Bitget 1m data, 7 symbols, at the 2.5x default width:
#   volume/day  = $1,949 per symbol per $10 of order size   (linear in both)
#   daily sigma = $1.81  per symbol at $10, scaling as n^0.82
#   peak inventory ≈ 11x order size per symbol
#
# sigma grows as n^0.82 while volume grows as n, so MORE symbols at SMALLER
# order sizes dominates: same volume, less risk. The sizer therefore spreads
# across every symbol it can before it grows an order.

VOL_PER_SYMBOL_PER_10 = 1949.0     # USD of volume per day
SIGMA_PER_SYMBOL_PER_10 = 1.81     # USD of daily P&L standard deviation
SIGMA_N_EXPONENT = 0.82
PEAK_INVENTORY_MULT = 11.0         # x order size, per symbol
EXCHANGE_MIN_ORDER = 5.0


@dataclass
class Sizing:
    ok: bool
    order_usdt: float
    symbols: int
    volume_per_day: float
    sigma_per_day: float
    sigma_pct: float               # sigma as a fraction of equity
    peak_inventory: float
    binding: str                   # which limit set the size
    reason: str = ""


def size_from_equity(equity: float,
                     available_symbols: int = 10,
                     risk_budget: float = 0.03,
                     max_gross_leverage: float = 5.0) -> Sizing:
    """
    Largest order size whose daily sigma stays inside `risk_budget` of equity
    and whose peak inventory stays inside `max_gross_leverage`.

    Returns ok=False when the answer is below the exchange minimum — at that
    point the honest move is not to trade, because the only way to place a $5
    order on too little equity is to accept a risk you did not choose.
    """
    if equity <= 0:
        return Sizing(False, 0, 0, 0, 0, 0, 0, "equity", "equity en cero")

    n = max(1, available_symbols)

    # Risk cap: sigma = SIGMA_PER_SYMBOL_PER_10 * (order/10) * n^0.82 <= budget*E
    risk_order = (risk_budget * equity * 10.0) / (SIGMA_PER_SYMBOL_PER_10 * n ** SIGMA_N_EXPONENT)
    # Margin cap: PEAK_INVENTORY_MULT * order * n <= max_gross_leverage * E
    margin_order = (max_gross_leverage * equity) / (PEAK_INVENTORY_MULT * n)

    order = min(risk_order, margin_order)
    binding = "riesgo" if risk_order <= margin_order else "margen"

    # Too small to place: drop symbols (sigma falls faster than the budget does)
    while order < EXCHANGE_MIN_ORDER and n > 1:
        n -= 1
        risk_order = (risk_budget * equity * 10.0) / (SIGMA_PER_SYMBOL_PER_10 * n ** SIGMA_N_EXPONENT)
        margin_order = (max_gross_leverage * equity) / (PEAK_INVENTORY_MULT * n)
        order = min(risk_order, margin_order)
        binding = "riesgo" if risk_order <= margin_order else "margen"

    if order < EXCHANGE_MIN_ORDER:
        needed = EXCHANGE_MIN_ORDER * SIGMA_PER_SYMBOL_PER_10 / (10.0 * risk_budget)
        return Sizing(False, order, n, 0, 0, 0, 0, binding,
                      f"orden de ${order:.2f} bajo el mínimo de ${EXCHANGE_MIN_ORDER:.0f}; "
                      f"con este presupuesto de riesgo hacen falta ~${needed:.0f} de equity")

    order = round(order, 2)
    sigma = SIGMA_PER_SYMBOL_PER_10 * (order / 10.0) * n ** SIGMA_N_EXPONENT
    return Sizing(
        ok=True, order_usdt=order, symbols=n,
        volume_per_day=VOL_PER_SYMBOL_PER_10 * (order / 10.0) * n,
        sigma_per_day=sigma, sigma_pct=sigma / equity,
        peak_inventory=PEAK_INVENTORY_MULT * order * n,
        binding=binding,
    )
