"""
Rebalance history in Upstash Redis, over its REST API.

Python on Vercel has no first-party storage SDK, but Upstash's REST interface is
plain HTTPS with a bearer token — no extra dependency, and a Redis list is
exactly the primitive for an append-only log.

Provision with `vercel integration add upstash`, which injects
UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN into the project.
"""

import json
import os
from typing import List, Optional

import requests

KEY = "xs:history"
MAX_RECORDS = 500          # ~16 months of daily runs; trimmed on every write


def _creds():
    url = os.getenv("UPSTASH_REDIS_REST_URL")
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
    return (url.rstrip("/"), token) if url and token else (None, None)


def enabled() -> bool:
    return all(_creds())


def _cmd(*args) -> Optional[dict]:
    """One Redis command. Storage is a convenience here, so failures never
    take the rebalance down with them — the trade matters, the log does not."""
    url, token = _creds()
    if not url:
        return None
    try:
        r = requests.post(url, headers={"Authorization": f"Bearer {token}"},
                          json=list(args), timeout=8)
        r.raise_for_status()
        return r.json()
    except requests.RequestException:
        return None


def append(record: dict) -> bool:
    if not enabled():
        return False
    ok = _cmd("LPUSH", KEY, json.dumps(record, separators=(",", ":")))
    if ok is not None:
        _cmd("LTRIM", KEY, 0, MAX_RECORDS - 1)
    return ok is not None


def history(limit: int = 90) -> List[dict]:
    if not enabled():
        return []
    resp = _cmd("LRANGE", KEY, 0, limit - 1)
    if not resp or "result" not in resp:
        return []
    out = []
    for raw in resp["result"]:
        try:
            out.append(json.loads(raw))
        except (ValueError, TypeError):
            continue
    return out
