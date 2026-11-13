"""
Cross-sectional momentum — live execution against Bitget (Unified v3).

Defaults to PAPER mode: it computes every signal and logs the order it would
send, but sends nothing. The backtest evidence for this strategy is weak
(p < 0.1), so the honest sequence is ~30 days of forward-test on data that did
not exist when the backtest ran, and only then real money.

    .venv/bin/python -m strategies.cross_sectional.strategy            # paper
    .venv/bin/python -m strategies.cross_sectional.strategy --live     # real orders
"""

import argparse
import logging
import os
import sys
import time
from typing import Dict, Optional

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.bitget_client import BitgetClient, unwrap
from shared.config import client_from_env
from strategies.cross_sectional.core import (
    CrossSectionalConfig, trailing_return, rank_universe,
    target_weights, sizing_is_viable,
)

logger = logging.getLogger("cross_sectional")


class CrossSectionalMomentum:
    def __init__(self, client: BitgetClient, cfg: CrossSectionalConfig):
        self.client = client
        self.cfg = cfg
        self.start_equity: Optional[float] = None
        self.rebalances = 0
        self.volume_usd = 0.0

    # ─── Market data ──────────────────────────────────────────────────────────

    def _closes(self, symbol: str) -> list:
        """Enough 1H bars to cover the lookback, plus slack for gaps."""
        need = self.cfg.lookback_hours + 5
        resp = self.client.get_kline(symbol, "1H", limit=min(need, 1000))
        rows = unwrap(resp)
        if not isinstance(rows, list) or not rows:
            return []
        # Bitget returns [ts, open, high, low, close, baseVol, quoteVol], oldest first
        return [float(r[4]) for r in rows]

    def compute_signals(self) -> Dict[str, float]:
        rets: Dict[str, Optional[float]] = {}
        for sym in self.cfg.universe:
            try:
                rets[sym] = trailing_return(self._closes(sym), self.cfg.lookback_hours)
            except Exception as e:
                logger.warning(f"{sym}: no se pudo calcular el retorno ({type(e).__name__})")
                rets[sym] = None
        longs, shorts = rank_universe(rets, self.cfg.k)
        if not longs:
            logger.warning("Ranking incompleto — no se opera este ciclo.")
            return {}
        logger.info(f"  largos : {', '.join(f'{s} {rets[s]*100:+.2f}%' for s in reversed(longs))}")
        logger.info(f"  cortos : {', '.join(f'{s} {rets[s]*100:+.2f}%' for s in shorts)}")
        return target_weights(longs, shorts, self.cfg.leverage)

    # ─── Account state ────────────────────────────────────────────────────────

    def equity(self) -> float:
        data = self.client.get_account().get("data") or {}
        return float(data.get("accountEquity") or 0)

    def current_positions(self) -> Dict[str, float]:
        """symbol -> signed USD notional currently held."""
        out: Dict[str, float] = {}
        for p in unwrap(self.client.get_positions()):
            try:
                sym = p["symbol"]
                notional = float(p.get("positionValue") or 0)
                side = str(p.get("posSide") or p.get("holdSide") or "").lower()
                out[sym] = -notional if side.startswith("short") else notional
            except (KeyError, TypeError, ValueError):
                continue
        return out

    # ─── Rebalance ────────────────────────────────────────────────────────────

    def rebalance(self):
        eq = self.equity()
        if self.start_equity is None:
            self.start_equity = eq
        if self.start_equity > 0:
            dd = eq / self.start_equity - 1
            if dd < -self.cfg.max_drawdown_pct:
                logger.error(f"🛑 Drawdown {dd*100:.1f}% supera el límite. Deteniendo.")
                raise SystemExit(1)

        ok, msg = sizing_is_viable(eq, self.cfg)
        # CI logs are public on a public repo; REDACT_BALANCES keeps account
        # size out of them. Signals stay visible — they are derivable from
        # public prices anyway, so hiding them buys nothing.
        if os.getenv("REDACT_BALANCES") == "1":
            logger.info(f"Equity [oculta] · sizing {'ok' if ok else 'insuficiente'}")
        else:
            logger.info(f"Equity ${eq:.2f} · {msg}")
        if not ok:
            logger.error("🛑 Capital insuficiente para ejecutar las 6 patas sin quedar descubierto.")
            return

        weights = self.compute_signals()
        if not weights:
            return

        current = self.current_positions()
        for sym in sorted(set(weights) | set(current)):
            target = weights.get(sym, 0.0) * eq
            have   = current.get(sym, 0.0)
            delta  = target - have
            if abs(delta) < self.cfg.min_order_usdt:
                continue
            side = "BUY" if delta > 0 else "SELL"
            px = float(unwrap(self.client.get_tickers(sym))[0]["lastPrice"])
            qty = abs(delta) / px
            self.volume_usd += abs(delta)

            redact = os.getenv("REDACT_BALANCES") == "1"
            monto = "[oculto]" if redact else f"${abs(delta):.2f}"
            if self.cfg.paper:
                extra = "" if redact else f" (tengo ${have:+.2f} → quiero ${target:+.2f})"
                logger.info(f"  [PAPEL] {side:<4} {sym:<10} {monto}{extra}")
            else:
                resp = self.client.place_order(sym, side, "MARKET", f"{qty:.6f}")
                mark = "✅" if resp.get("code") == "00000" else f"❌ {resp.get('msg')}"
                logger.info(f"  [REAL] {side:<4} {sym:<10} {monto}  {mark}")
        self.rebalances += 1

    def run(self):
        modo = "PAPEL (no manda órdenes)" if self.cfg.paper else "⚠️  REAL (dinero de verdad)"
        logger.info(f"Cross-sectional momentum · {modo}")
        logger.info(f"  universo {len(self.cfg.universe)} activos · lookback "
                    f"{self.cfg.lookback_hours}h · rebalanceo {self.cfg.hold_hours}h · K={self.cfg.k}")
        while True:
            try:
                self.rebalance()
                vol = "[oculto]" if os.getenv("REDACT_BALANCES") == "1" \
                      else f"${self.volume_usd:,.0f}"
                logger.info(f"  acumulado: {self.rebalances} rebalanceos · "
                            f"{vol} de volumen\n")
            except SystemExit:
                raise
            except Exception as e:
                logger.error(f"Ciclo falló: {type(e).__name__}: {e}")
            time.sleep(self.cfg.hold_hours * 3600)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="mandar órdenes reales")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--lookback", type=int, default=168)
    ap.add_argument("--hold", type=int, default=24)
    ap.add_argument("--leverage", type=float, default=2.0)
    ap.add_argument("--once", action="store_true", help="un solo ciclo y salir")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s",
                        datefmt="%H:%M:%S")
    load_dotenv()
    # Even paper mode reads account equity to size positions, so keys are required.
    client = client_from_env()
    if client.demo:
        logging.info("Entorno DEMO de Bitget (paptrading): fondos simulados.")
    cfg = CrossSectionalConfig(k=args.k, lookback_hours=args.lookback,
                               hold_hours=args.hold, leverage=args.leverage,
                               paper=not args.live)
    bot = CrossSectionalMomentum(client, cfg)
    if args.once:
        bot.rebalance()
    else:
        bot.run()


if __name__ == "__main__":
    main()
