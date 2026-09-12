"""
Cross-sectional momentum — signal logic, no I/O.

Ranks a universe by trailing return and holds the strongest K long against the
weakest K short. It never predicts one asset's direction; the bet is that
relative strength persists for a few days. Being long and short in equal size
cancels most market exposure, leaving only the dispersion between assets.

Validated 2026-09-12 on 360d of Bitget 1H data over a survivorship-free major
universe: walk-forward Sharpe 1.56, +42.9% out-of-sample, max drawdown -24.1%,
against a null averaging -0.73 Sharpe (0 of 10 shuffled runs reached it).
That is weak evidence (p < 0.1), not proof — forward-test before funding.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Majors that were already liquid a year ago. Picking the universe by today's
# turnover is lookahead: an asset makes that list partly because it pumped, and
# momentum over a pumped-into-existence universe backtests beautifully for
# reasons that cannot be traded.
DEFAULT_UNIVERSE = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "LINKUSDT", "XLMUSDT", "UNIUSDT", "NEARUSDT", "SUIUSDT",
]


@dataclass
class CrossSectionalConfig:
    universe: List[str] = field(default_factory=lambda: list(DEFAULT_UNIVERSE))

    # Trailing window used for ranking, in hours. 168h = 7 days.
    lookback_hours: int = 168

    # Hours between rebalances. 24h = daily.
    hold_hours: int = 24

    # Legs per side: K long + K short. K=3 over 12 assets is the top/bottom quartile.
    k: int = 3

    # Gross exposure as a multiple of equity. Each of the 2K legs gets
    # leverage/(2K) of equity, which must clear the exchange's $5 minimum.
    leverage: float = 2.0

    # Exchange minimum order size in USDT.
    min_order_usdt: float = 5.0

    # Stop trading if equity falls this far below the session start.
    max_drawdown_pct: float = 0.30

    paper: bool = True


def trailing_return(closes: List[float], lookback_bars: int) -> Optional[float]:
    """Return over the last `lookback_bars`, or None when history is short."""
    if len(closes) < lookback_bars + 1:
        return None
    old = closes[-(lookback_bars + 1)]
    if old <= 0:
        return None
    return closes[-1] / old - 1.0


def rank_universe(returns: Dict[str, Optional[float]], k: int):
    """
    Split the universe into the K strongest and K weakest.
    Returns (longs, shorts); both empty when fewer than 2K assets have data,
    since a partial ranking is not the strategy — it is a directional bet.
    """
    valid = {s: r for s, r in returns.items() if r is not None}
    if len(valid) < 2 * k:
        return [], []
    ordered = sorted(valid, key=lambda s: valid[s])
    return ordered[-k:], ordered[:k]


def target_weights(longs: List[str], shorts: List[str], leverage: float) -> Dict[str, float]:
    """Equal-weight each leg so the book is dollar-neutral."""
    if not longs or not shorts:
        return {}
    per_leg = leverage / (len(longs) + len(shorts))
    w = {s: per_leg for s in longs}
    w.update({s: -per_leg for s in shorts})
    return w


def sizing_is_viable(equity: float, cfg: CrossSectionalConfig) -> tuple[bool, str]:
    """
    Each leg must clear the exchange minimum or the book ends up lopsided —
    some legs placed, others rejected, leaving unhedged directional risk.
    """
    per_leg = equity * cfg.leverage / (2 * cfg.k)
    if per_leg < cfg.min_order_usdt:
        needed = cfg.min_order_usdt * 2 * cfg.k / cfg.leverage
        return False, (f"cada pata sería ${per_leg:.2f}, bajo el mínimo de "
                       f"${cfg.min_order_usdt}. Necesitas ${needed:.2f} de equity "
                       f"a {cfg.leverage}x, o subir el apalancamiento.")
    return True, f"cada pata ${per_leg:.2f} · {2*cfg.k} patas · bruto ${equity*cfg.leverage:.2f}"
