"""
Tiny status endpoint served from inside the bot process.

Replaces an external store for this purpose: the bot already holds its own
state, so publishing it needs a socket, not a database. /health backs the
container healthcheck; /status is what a dashboard reads.

Bound to localhost by default. Put it behind a reverse proxy with auth if you
want it reachable — the payload includes position sizes.
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logger = logging.getLogger("mm.status")

_state = {"started": None, "last_cycle": None, "quotes": {}, "inventory": {},
          "equity": None, "order_usdt": None, "symbols": [], "sizing": None,
          "volume_usd": 0.0, "fills": 0, "mode": "paper", "errors": []}
_lock = threading.Lock()


def update(**kw):
    with _lock:
        _state.update(kw)
        _state["last_cycle"] = datetime.now(timezone.utc).isoformat(timespec="seconds")


def note_error(msg: str):
    with _lock:
        _state["errors"] = ([{"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                              "msg": msg}] + _state["errors"])[:20]


def snapshot() -> dict:
    with _lock:
        return json.loads(json.dumps(_state, default=str))


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/health"):
            # Healthy means a cycle completed recently, not merely that the
            # process is alive — a bot stuck mid-loop still answers a socket.
            snap = snapshot()
            stale = True
            if snap.get("last_cycle"):
                age = (datetime.now(timezone.utc) -
                       datetime.fromisoformat(snap["last_cycle"])).total_seconds()
                stale = age > 300
            self._send(503 if stale else 200,
                       {"ok": not stale, "last_cycle": snap.get("last_cycle")})
        elif self.path.startswith("/status"):
            self._send(200, snapshot())
        else:
            self._send(404, {"error": "not found"})

    def _send(self, code, payload):
        body = json.dumps(payload, indent=2, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass          # the bot's own logger is the record; this would double it


def start(port: int = None, host: str = None):
    port = port or int(os.getenv("STATUS_PORT", "8080"))
    host = host or os.getenv("STATUS_HOST", "0.0.0.0")
    srv = ThreadingHTTPServer((host, port), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    update(started=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    logger.info(f"  estado en http://{host}:{port}/status")
    return srv
