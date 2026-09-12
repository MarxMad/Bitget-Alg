"""
Daily rebalance, triggered by Vercel Cron.

Vercel sends `Authorization: Bearer $CRON_SECRET` when that env var is set, so
the endpoint refuses anything else. Without it, a public URL would let anyone on
the internet fire a rebalance at will.
"""

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import _store
from shared.bitget_client import BitgetClient, unwrap
from strategies.cross_sectional.core import (
    CrossSectionalConfig, trailing_return, rank_universe,
    target_weights, sizing_is_viable,
)


def _client() -> BitgetClient:
    return BitgetClient(
        os.environ["BITGET_ACCESS_KEY"],
        os.environ["BITGET_PASSPHRASE"],
        os.environ["BITGET_PRIVATE_KEY"],   # the PEM itself, not a path
    )


def run_rebalance(live: bool) -> dict:
    cfg = CrossSectionalConfig(paper=not live)
    c = _client()

    rets = {}
    for sym in cfg.universe:
        try:
            rows = unwrap(c.get_kline(sym, "1H", limit=cfg.lookback_hours + 5))
            rets[sym] = trailing_return([float(r[4]) for r in rows], cfg.lookback_hours)
        except Exception:
            rets[sym] = None

    longs, shorts = rank_universe(rets, cfg.k)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "live" if live else "paper",
        "returns": {s: (round(v, 5) if v is not None else None) for s, v in rets.items()},
        "longs": longs, "shorts": shorts,
        "orders": [], "equity": None, "skipped": None,
    }

    if not longs:
        record["skipped"] = "ranking incompleto: faltan datos de suficientes activos"
        _store.append(record)
        return record

    account = c.get_account().get("data") or {}
    equity = float(account.get("accountEquity") or 0)
    record["equity"] = equity

    ok, msg = sizing_is_viable(equity, cfg)
    if not ok:
        record["skipped"] = msg
        _store.append(record)
        return record

    current = {}
    for p in unwrap(c.get_positions()):
        try:
            side = str(p.get("posSide") or p.get("holdSide") or "").lower()
            notional = float(p.get("positionValue") or 0)
            current[p["symbol"]] = -notional if side.startswith("short") else notional
        except (KeyError, TypeError, ValueError):
            continue

    weights = target_weights(longs, shorts, cfg.leverage)
    for sym in sorted(set(weights) | set(current)):
        target = weights.get(sym, 0.0) * equity
        delta = target - current.get(sym, 0.0)
        if abs(delta) < cfg.min_order_usdt:
            continue
        side = "BUY" if delta > 0 else "SELL"
        entry = {"symbol": sym, "side": side, "usd": round(abs(delta), 2)}
        if live:
            px = float(unwrap(c.get_tickers(sym))[0]["lastPrice"])
            resp = c.place_order(sym, side, "MARKET", f"{abs(delta)/px:.6f}")
            entry["ok"] = resp.get("code") == "00000"
            if not entry["ok"]:
                entry["error"] = resp.get("msg")
        record["orders"].append(entry)

    record["volume_usd"] = round(sum(o["usd"] for o in record["orders"]), 2)
    _store.append(record)
    return record


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        secret = os.getenv("CRON_SECRET")
        if secret and self.headers.get("Authorization") != f"Bearer {secret}":
            self._send(401, {"error": "unauthorized"})
            return
        if not secret:
            self._send(500, {"error": "CRON_SECRET no configurado — endpoint deshabilitado"})
            return
        try:
            result = run_rebalance(live=os.getenv("TRADING_MODE") == "live")
            self._send(200, result)
        except Exception as e:
            self._send(500, {"error": f"{type(e).__name__}: {e}",
                             "trace": traceback.format_exc()[-800:]})

    def _send(self, code, payload):
        body = json.dumps(payload, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
