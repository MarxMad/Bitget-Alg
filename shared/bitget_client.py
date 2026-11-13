"""
Bitget Unified Trading Account (UTA / v3) REST API Client
Base URL: https://api.bitget.com

Signs requests with either of the two key types Bitget issues:
  * HMAC-SHA256 — the default "system-generated" key (API key + secret). This
    is what workshop attendees create.
  * RSA-SHA256  — a self-generated key pair whose public half is uploaded.
Demo (paper) trading uses a separate Demo API key plus the header
`paptrading: 1` on every request; pass demo=True.

Keeps a small, stable method surface so
strategies can swap exchanges by changing only the client construction.

Signature scheme:
    prehash = timestamp + METHOD + requestPath(+query) + body
    sign    = base64( RSA-PKCS1v15-SHA256( private_key, prehash ) )

Endpoint shapes below were verified against the live API on 2026-09-12.
The v3 API is NOT the same as v2/Mix: an account in Unified mode is rejected
from every v2 private endpoint with code 40085.
"""

import base64
import hashlib
import hmac
import time
import json
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urlencode
from typing import Optional, Dict, Any, List

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

logger = logging.getLogger(__name__)

BASE_URL = "https://api.bitget.com"
CATEGORY = "USDT-FUTURES"


def _load_private_key(path_or_pem: str):
    """Accept either a filesystem path to a PEM file or the PEM text itself."""
    if "BEGIN" in path_or_pem:
        pem_bytes = path_or_pem.encode("utf-8")
    else:
        with open(path_or_pem, "rb") as f:
            pem_bytes = f.read()
    return serialization.load_pem_private_key(pem_bytes, password=None)


def unwrap(resp: dict) -> Any:
    """
    v3 wraps most collections as {"data": {"list": [...], "cursor": ...}} and
    returns list=None (not []) when empty. Callers want the plain list.

    Endpoints whose data is a single object (e.g. /account/assets) are returned
    as-is: never wrap one in a list, or len() silently counts its FIELDS and a
    zero-balance account reads as 14 assets.
    """
    data = resp.get("data")
    if isinstance(data, dict) and "list" in data:
        return data["list"] or []
    if data is None:
        return []
    return data


class BitgetClient:
    """Synchronous REST client for Bitget USDT-M Futures on the Unified (v3) API."""

    def __init__(self, access_key: str = "", passphrase: str = "",
                 private_key: Optional[str] = None,
                 timeout: int = 15, category: str = CATEGORY,
                 secret_key: Optional[str] = None, demo: bool = False):
        self.access_key = access_key
        self.passphrase = passphrase
        # Public market endpoints need no credentials, so a key-less client is valid.
        # A secret selects HMAC; a private key selects RSA. Never both, because
        # silently preferring one would hide a misconfigured .env.
        if secret_key and private_key:
            raise ValueError("Pass secret_key (HMAC) or private_key (RSA), not both.")
        self.secret_key = secret_key or None
        self.private_key = _load_private_key(private_key) if private_key else None
        self.demo = demo
        self.category = category
        self.timeout = timeout

        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json",
                                     "locale": "en-US"})
        retry = Retry(
            total=3,
            backoff_factor=1.5,
            status_forcelist=[502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    # ─── Signing ──────────────────────────────────────────────────────────────

    def _sign(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        """HMAC-SHA256 (secret) or RSA-PKCS1v15-SHA256 (private key) over the
        prehash string, base64-encoded. Bitget uses the same prehash for both."""
        prehash = f"{timestamp}{method.upper()}{request_path}{body}"
        if self.secret_key:
            digest = hmac.new(self.secret_key.encode("utf-8"),
                              prehash.encode("utf-8"), hashlib.sha256).digest()
            return base64.b64encode(digest).decode("utf-8")
        if self.private_key is None:
            raise RuntimeError("This call needs credentials: no secret or private key loaded.")
        signature = self.private_key.sign(
            prehash.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")

    def _make_headers(self, timestamp: str, sign: str) -> dict:
        return {
            "ACCESS-KEY": self.access_key,
            "ACCESS-SIGN": sign,
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
            "locale": "en-US",
        }

    def _request(self, method: str, path: str, params: Optional[Dict] = None,
                 body: Optional[Dict] = None, signed: bool = True) -> dict:
        params = params or {}
        # Bitget signs the path WITH the query string appended, so it must be
        # built once and reused verbatim for both the signature and the URL.
        query = urlencode(params) if params else ""
        request_path = path + (f"?{query}" if query else "")
        body_str = json.dumps(body, separators=(",", ":")) if body else ""

        headers = {}
        if signed:
            timestamp = str(int(time.time() * 1000))
            sign = self._sign(timestamp, method, request_path, body_str)
            headers = self._make_headers(timestamp, sign)
        if self.demo:
            # Routes the call to the demo (paper) environment. Sent on public
            # calls too, so prices and contract specs match the demo market.
            headers["paptrading"] = "1"

        url = BASE_URL + request_path
        try:
            resp = self.session.request(method, url, data=body_str or None,
                                        headers=headers or None, timeout=self.timeout)
            # Bitget returns its real error code/msg in the body of a 4xx, so parse
            # the JSON before deciding to raise — raise_for_status() would hide it.
            try:
                data = resp.json()
            except ValueError:
                resp.raise_for_status()
                raise
            if data.get("code") not in ("00000", None):
                logger.warning(f"{method} {path} -> code={data.get('code')} msg={data.get('msg')}")
            return data
        except requests.RequestException as e:
            logger.error(f"{method} {path} failed: {e}")
            raise

    def _get(self, path: str, params: Optional[Dict] = None, signed: bool = True) -> dict:
        return self._request("GET", path, params=params, signed=signed)

    def _post(self, path: str, body: Optional[Dict] = None) -> dict:
        return self._request("POST", path, body=body, signed=True)

    # ─── Public Market Endpoints ──────────────────────────────────────────────

    def get_tickers(self, symbol: Optional[str] = None) -> dict:
        """Ticker(s). Omit symbol for all ~790 contracts in one call."""
        params = {"category": self.category}
        if symbol:
            params["symbol"] = symbol
        return self._get("/api/v3/market/tickers", params, signed=False)

    def get_depth(self, symbol: str, limit: int = 20) -> dict:
        """Order book."""
        return self._get("/api/v3/market/orderbook",
                         {"category": self.category, "symbol": symbol,
                          "limit": str(limit)}, signed=False)

    def get_kline(self, symbol: str, granularity: str = "1m", limit: int = 100) -> dict:
        """
        Candles. v3 names this parameter `interval`, not `granularity` — passing
        `granularity` fails with 400172 regardless of its value.
        Returns [ts, open, high, low, close, baseVol, quoteVol].
        """
        return self._get("/api/v3/market/candles",
                         {"category": self.category, "symbol": symbol,
                          "interval": granularity, "limit": str(limit)}, signed=False)

    def get_instruments(self, symbol: Optional[str] = None) -> dict:
        """Contract specs: tick size, min qty, min notional, max leverage."""
        params = {"category": self.category}
        if symbol:
            params["symbol"] = symbol
        return self._get("/api/v3/market/instruments", params, signed=False)

    def get_recent_fills(self, symbol: str, limit: int = 50) -> dict:
        """Recent public trades (everyone's, not yours)."""
        return self._get("/api/v3/market/fills",
                         {"category": self.category, "symbol": symbol,
                          "limit": str(limit)}, signed=False)

    def get_funding_rate(self, symbol: str) -> dict:
        """Current perpetual funding rate."""
        return self._get("/api/v3/market/current-fund-rate",
                         {"category": self.category, "symbol": symbol}, signed=False)

    # ─── Account Endpoints ────────────────────────────────────────────────────

    def get_account(self, margin_coin: str = "USDT") -> dict:
        """Account assets. Needs the 'UTA manage read' permission on the API key."""
        return self._get("/api/v3/account/assets", {})

    def get_settings(self) -> dict:
        """Account mode/settings. Needs 'UTA manage read'."""
        return self._get("/api/v3/account/settings", {})

    def get_positions(self, symbol: Optional[str] = None) -> dict:
        """Open positions."""
        params = {"category": self.category}
        if symbol:
            params["symbol"] = symbol
        return self._get("/api/v3/position/current-position", params)

    def set_leverage(self, symbol: str, leverage: int, margin_coin: str = "USDT") -> dict:
        """Change leverage for a symbol."""
        return self._post("/api/v3/account/set-leverage",
                          {"category": self.category, "symbol": symbol,
                           "marginCoin": margin_coin, "leverage": str(leverage)})

    # ─── Order Endpoints ──────────────────────────────────────────────────────

    def place_order(self, symbol: str, side: str, order_type: str,
                    qty: str, price: Optional[str] = None,
                    reduce_only: bool = False,
                    time_in_force: str = "GTC",
                    client_id: Optional[str] = None,
                    pos_side: Optional[str] = None) -> dict:
        """
        Place a single order.
        side: BUY | SELL          order_type: LIMIT | MARKET
        pos_side: long | short    (hedge mode only; omit in one-way mode)
        """
        tif_map = {"GTC": "gtc", "IOC": "ioc", "FOK": "fok", "POST_ONLY": "post_only"}
        body: Dict[str, Any] = {
            "category": self.category,
            "symbol": symbol,
            "side": side.lower(),
            "orderType": order_type.lower(),
            "qty": str(qty),
            "timeInForce": tif_map.get(time_in_force.upper(), "gtc"),
        }
        if price:
            body["price"] = str(price)
        if client_id:
            body["clientOid"] = client_id
        if reduce_only:
            body["reduceOnly"] = "YES"
        if pos_side:
            body["posSide"] = pos_side.lower()
        return self._post("/api/v3/trade/place-order", body)

    def cancel_order(self, symbol: str, order_id: Optional[str] = None,
                     client_id: Optional[str] = None) -> dict:
        """Cancel one order by exchange id or client id."""
        body = {"category": self.category, "symbol": symbol}
        if order_id:
            body["orderId"] = order_id
        if client_id:
            body["clientOid"] = client_id
        return self._post("/api/v3/trade/cancel-order", body)

    def cancel_all_orders(self, symbol: Optional[str] = None) -> dict:
        """Cancel all open orders (optionally scoped to one symbol)."""
        body = {"category": self.category}
        if symbol:
            body["symbol"] = symbol
        return self._post("/api/v3/trade/cancel-all-orders", body)

    def get_pending_orders(self, symbol: Optional[str] = None) -> dict:
        """Open/unfilled orders."""
        params = {"category": self.category}
        if symbol:
            params["symbol"] = symbol
        return self._get("/api/v3/trade/unfilled-orders", params)

    def close_positions(self, symbol: str, pos_side: Optional[str] = None) -> dict:
        """Market-close an open position."""
        body = {"category": self.category, "symbol": symbol}
        if pos_side:
            body["posSide"] = pos_side.lower()
        return self._post("/api/v3/trade/close-positions", body)

    # Kept for interface compatibility.
    flash_close_position = close_positions
