"""
Read-only state for the dashboard: live signals plus stored rebalance history.

Placing no orders, it needs no CRON_SECRET — the deployment itself is private
behind Vercel Authentication, which is what keeps this from being public.
"""

import json
import os
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import _store
from shared.bitget_client import BitgetClient, unwrap
from strategies.cross_sectional.core import (
    CrossSectionalConfig, trailing_return, rank_universe,
)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        cfg = CrossSectionalConfig()
        out = {
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "mode": os.getenv("TRADING_MODE", "paper"),
            "config": {"lookback_hours": cfg.lookback_hours, "hold_hours": cfg.hold_hours,
                       "k": cfg.k, "leverage": cfg.leverage,
                       "universe": len(cfg.universe)},
            "storage": _store.enabled(),
        }
        try:
            pub = BitgetClient()
            rets = {}
            for sym in cfg.universe:
                try:
                    rows = unwrap(pub.get_kline(sym, "1H", limit=cfg.lookback_hours + 5))
                    rets[sym] = trailing_return([float(r[4]) for r in rows], cfg.lookback_hours)
                except Exception:
                    rets[sym] = None
            longs, shorts = rank_universe(rets, cfg.k)
            out["ranking"] = sorted(
                ({"symbol": s, "ret": r, "leg": "long" if s in longs else
                  "short" if s in shorts else "flat"}
                 for s, r in rets.items() if r is not None),
                key=lambda x: -x["ret"])
        except Exception as e:
            out["ranking_error"] = f"{type(e).__name__}: {e}"

        try:
            creds = all(os.getenv(k) for k in
                        ("BITGET_ACCESS_KEY", "BITGET_PASSPHRASE", "BITGET_PRIVATE_KEY"))
            if creds:
                c = BitgetClient(os.environ["BITGET_ACCESS_KEY"],
                                 os.environ["BITGET_PASSPHRASE"],
                                 os.environ["BITGET_PRIVATE_KEY"])
                acct = c.get_account().get("data") or {}
                out["equity"] = float(acct.get("accountEquity") or 0)
                out["positions"] = [
                    {"symbol": p.get("symbol"),
                     "side": str(p.get("posSide") or p.get("holdSide") or ""),
                     "value": float(p.get("positionValue") or 0),
                     "pnl": float(p.get("unrealisedPnl") or p.get("unrealizedPL") or 0)}
                    for p in unwrap(c.get_positions())]
        except Exception as e:
            out["account_error"] = f"{type(e).__name__}: {e}"

        out["history"] = _store.history(90)
        body = json.dumps(out, indent=2).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
