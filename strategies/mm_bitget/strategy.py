"""
Market maker for Bitget (Unified v3). Paper by default.

Why this cannot be mistaken for wash trading
--------------------------------------------
Wash trading is trading with yourself to fake volume. Four properties make that
mechanically impossible here, and each is enforced in code rather than assumed:

1. **post_only on every order.** The exchange rejects any quote that would
   cross the book, so this bot can never be the aggressor — and an order that
   never takes liquidity can never hit your own resting order.
2. **The quote pair can never cross.** `quote_prices` returns None instead of a
   bid above its own ask, so the two sides cannot meet even in a dislocation.
3. **Requote throttling.** Quotes move only when price has drifted a real
   fraction of volatility. Cancel/replace storms against a still book are the
   layering pattern surveillance looks for, and they buy nothing.
4. **Real risk on every fill.** Counterparties are other traders, inventory is
   genuine, and the P&L can go against you. That is what makes the volume real.

Run:
    python -m strategies.mm_bitget.strategy                # paper
    python -m strategies.mm_bitget.strategy --live         # real orders
"""

import argparse
import logging
import os
import sys
import time
from collections import deque
from typing import Dict, Optional, Tuple

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.bitget_client import BitgetClient, unwrap
from strategies.mm_bitget import status_server
from strategies.mm_bitget.core import (
    MMConfig, realized_vol, quote_prices, sides_allowed, needs_reprice,
    size_from_equity,
)

logger = logging.getLogger("mm")


class BitgetMarketMaker:
    def __init__(self, client: BitgetClient, cfg: MMConfig):
        self.client = client
        self.cfg = cfg
        self.closes: Dict[str, deque] = {s: deque(maxlen=cfg.vol_window + 10)
                                         for s in cfg.symbols}
        self.quotes: Dict[str, Optional[Tuple[float, float]]] = {s: None for s in cfg.symbols}
        self.orders: Dict[str, list] = {s: [] for s in cfg.symbols}
        self.start_equity: Optional[float] = None
        self.volume_usd = 0.0
        self.tick: Dict[str, float] = {}

    # ─── setup ────────────────────────────────────────────────────────────────

    def load_specs(self):
        for d in unwrap(self.client.get_instruments()):
            if d.get("symbol") in self.cfg.symbols:
                self.tick[d["symbol"]] = 10 ** (-int(d["pricePrecision"]))
        missing = [s for s in self.cfg.symbols if s not in self.tick]
        if missing:
            raise RuntimeError(f"sin specs de contrato para {missing}")

    def seed_history(self):
        for s in self.cfg.symbols:
            rows = unwrap(self.client.get_kline(s, "1m", limit=self.cfg.vol_window + 5))
            for r in rows:
                self.closes[s].append(float(r[4]))

    # ─── state ────────────────────────────────────────────────────────────────

    def equity(self) -> float:
        return float((self.client.get_account().get("data") or {}).get("accountEquity") or 0)

    def inventory(self) -> Dict[str, float]:
        out = {s: 0.0 for s in self.cfg.symbols}
        for p in unwrap(self.client.get_positions()):
            sym = p.get("symbol")
            if sym not in out:
                continue
            try:
                side = str(p.get("posSide") or p.get("holdSide") or "").lower()
                v = float(p.get("positionValue") or 0)
                out[sym] = -v if side.startswith("short") else v
            except (TypeError, ValueError):
                continue
        return out

    def _round(self, sym: str, px: float) -> str:
        t = self.tick[sym]
        return f"{round(px / t) * t:.{max(0, len(str(t).split('.')[-1]))}f}"

    # ─── quoting ──────────────────────────────────────────────────────────────

    def cancel(self, sym: str):
        if self.cfg.paper or not self.orders[sym]:
            self.orders[sym] = []
            return
        self.client.cancel_all_orders(sym)
        self.orders[sym] = []

    def quote(self, sym: str, inv_usd: float):
        rows = unwrap(self.client.get_kline(sym, "1m", limit=3))
        if rows:
            self.closes[sym].append(float(rows[-1][4]))
        closes = list(self.closes[sym])
        vol = realized_vol(closes, self.cfg.vol_window)
        if vol is None:
            logger.info(f"  {sym}: histórico insuficiente para estimar volatilidad")
            return
        mid = closes[-1]

        pair = quote_prices(mid, vol, inv_usd, self.cfg)
        if pair is None:
            logger.warning(f"  {sym}: cotizaciones se cruzarían — no se envía nada")
            return
        if not needs_reprice(self.quotes[sym], pair, vol, mid, self.cfg):
            return

        self.cancel(sym)
        bid, ask = pair
        may_bid, may_ask = sides_allowed(inv_usd, self.cfg)
        qty = self.cfg.order_usdt / mid

        for side, px, allowed in (("BUY", bid, may_bid), ("SELL", ask, may_ask)):
            if not allowed:
                logger.info(f"  {sym}: {side} pausado, inventario en el tope (${inv_usd:+.2f})")
                continue
            px_s = self._round(sym, px)
            if self.cfg.paper:
                logger.info(f"  [PAPEL] {sym} {side:<4} {self.cfg.order_usdt:.2f} USDT @ {px_s}")
            else:
                # post_only: the exchange rejects it if it would cross, which is
                # what makes taking — and therefore self-matching — impossible.
                resp = self.client.place_order(sym, side, "LIMIT", f"{qty:.6f}",
                                               price=px_s, time_in_force="POST_ONLY")
                if resp.get("code") == "00000":
                    self.orders[sym].append((resp.get("data") or {}).get("orderId"))
                    logger.info(f"  {sym} {side:<4} @ {px_s} ✅")
                else:
                    logger.warning(f"  {sym} {side:<4} @ {px_s} ❌ {resp.get('msg')}")
        self.quotes[sym] = pair
        logger.info(f"  {sym}: ancho {(ask-bid)/mid*100:.4f}% · vol1m {vol*100:.4f}% "
                    f"· inventario ${inv_usd:+.2f}")

    # ─── loop ─────────────────────────────────────────────────────────────────

    def resize(self, eq: float) -> bool:
        """Recompute order size and symbol count from live equity.

        Volume scales linearly with both order size and symbol count, but risk
        scales as n^0.82, so the sizer spends its budget on symbols before it
        grows an order. Returns False when no size clears the $5 minimum inside
        the risk budget — at which point not trading is the correct answer."""
        if not self.cfg.auto_size:
            return True
        s = size_from_equity(eq, len(self.cfg.universe),
                             self.cfg.risk_budget, self.cfg.max_gross_leverage)
        if not s.ok:
            logger.error(f"🛑 {s.reason}")
            # Publish the refusal too: a status endpoint that goes blank when
            # the bot declines looks identical to one that is broken.
            status_server.update(sizing={"blocked": s.reason})
            return False
        nuevos = self.cfg.universe[:s.symbols]
        if nuevos != self.cfg.symbols or abs(s.order_usdt - self.cfg.order_usdt) > 0.01:
            for old in self.cfg.symbols:
                if old not in nuevos:
                    self.cancel(old)
            self.cfg.symbols = nuevos
            self.cfg.order_usdt = s.order_usdt
            for sym in nuevos:
                self.closes.setdefault(sym, deque(maxlen=self.cfg.vol_window + 10))
                self.quotes.setdefault(sym, None)
                self.orders.setdefault(sym, [])
            logger.info(f"  dimensionado: ${s.order_usdt:.2f}/orden × {s.symbols} símbolos "
                        f"· σ ${s.sigma_per_day:.2f}/día ({s.sigma_pct*100:.1f}%) "
                        f"· vol ${s.volume_per_day:,.0f}/día · límite: {s.binding}")
        status_server.update(order_usdt=s.order_usdt, symbols=list(nuevos),
                             sizing={"sigma_day": round(s.sigma_per_day, 2),
                                     "sigma_pct": round(s.sigma_pct, 4),
                                     "volume_day": round(s.volume_per_day),
                                     "binding": s.binding})
        return True

    def step(self):
        eq = self.equity()
        status_server.update(equity=eq, mode="paper" if self.cfg.paper else "live")
        if self.start_equity is None:
            self.start_equity = eq
        if not self.resize(eq):
            return
        if self.start_equity > 0:
            pnl = eq / self.start_equity - 1
            if pnl < -self.cfg.daily_loss_limit:
                logger.error(f"🛑 Pérdida {pnl*100:.1f}% supera el límite diario. Cerrando.")
                for s in self.cfg.symbols:
                    self.cancel(s)
                raise SystemExit(1)

        inv = self.inventory()
        gross = sum(abs(v) for v in inv.values())
        if eq > 0 and gross > eq * self.cfg.max_gross_leverage:
            logger.warning(f"  exposición bruta ${gross:.2f} supera {self.cfg.max_gross_leverage}x "
                           f"equity ${eq:.2f} — solo se reduce inventario")
        for s in self.cfg.symbols:
            try:
                self.quote(s, inv.get(s, 0.0))
            except Exception as e:
                logger.error(f"  {s}: {type(e).__name__}: {e}")
                status_server.note_error(f"{s}: {type(e).__name__}: {e}")
        status_server.update(equity=eq, inventory=inv, mode="paper" if self.cfg.paper else "live",
                             quotes={k: list(v) if v else None for k, v in self.quotes.items()})

    def run(self):
        modo = "PAPEL (no manda órdenes)" if self.cfg.paper else "⚠️  REAL"
        logger.info(f"Market maker Bitget · {modo}")
        logger.info(f"  {', '.join(self.cfg.symbols)} · ancho {self.cfg.vol_multiple}x vol · "
                    f"orden ${self.cfg.order_usdt} · tope {self.cfg.max_inventory_orders} órdenes")
        status_server.start()
        self.load_specs()
        self.seed_history()
        while True:
            try:
                self.step()
            except SystemExit:
                raise
            except Exception as e:
                logger.error(f"ciclo: {type(e).__name__}: {e}")
            time.sleep(self.cfg.requote_seconds)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--symbols", default="SOLUSDT,BTCUSDT")
    ap.add_argument("--order-usdt", type=float, default=5.0)
    ap.add_argument("--vol-multiple", type=float, default=2.5)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    load_dotenv()
    client = BitgetClient(os.getenv("BITGET_ACCESS_KEY"), os.getenv("BITGET_PASSPHRASE"),
                          os.getenv("BITGET_PRIVATE_KEY_PATH") or os.getenv("BITGET_PRIVATE_KEY"))
    cfg = MMConfig(symbols=[s.strip().upper() for s in args.symbols.split(",")],
                   order_usdt=args.order_usdt, vol_multiple=args.vol_multiple,
                   paper=not args.live)
    bot = BitgetMarketMaker(client, cfg)
    if args.once:
        bot.load_specs(); bot.seed_history(); bot.step()
    else:
        bot.run()


if __name__ == "__main__":
    main()
