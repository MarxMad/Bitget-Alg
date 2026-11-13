"""
Builds a BitgetClient from environment variables (usually loaded from .env).

One place decides which key type and which environment to use, so every
strategy and tool reads credentials the same way.

    BITGET_API_KEY           API key (BITGET_ACCESS_KEY also accepted)
    BITGET_PASSPHRASE        passphrase chosen when the key was created
    BITGET_SECRET_KEY        secret of a system-generated key  -> HMAC signing
    BITGET_PRIVATE_KEY_PATH  path to an RSA private key (.pem)  -> RSA signing
    BITGET_PRIVATE_KEY       the PEM text itself, instead of a path
    BITGET_DEMO              "1" = demo (paper) trading with a Demo API key

Set the secret OR the private key, never both.
"""

import os
from typing import List

from shared.bitget_client import BitgetClient


def _env(*names: str) -> str:
    for n in names:
        v = os.getenv(n, "").strip()
        if v:
            return v
    return ""


def is_demo() -> bool:
    return os.getenv("BITGET_DEMO", "0").strip().lower() in ("1", "true", "yes", "si", "sí")


def missing_credentials() -> List[str]:
    """Names of the variables still missing for a private (signed) client."""
    missing = []
    if not _env("BITGET_API_KEY", "BITGET_ACCESS_KEY"):
        missing.append("BITGET_API_KEY")
    if not _env("BITGET_PASSPHRASE"):
        missing.append("BITGET_PASSPHRASE")
    if not _env("BITGET_SECRET_KEY", "BITGET_PRIVATE_KEY_PATH", "BITGET_PRIVATE_KEY"):
        missing.append("BITGET_SECRET_KEY")
    return missing


def auth_method() -> str:
    return "HMAC" if _env("BITGET_SECRET_KEY") else "RSA"


def client_from_env(public_only: bool = False) -> BitgetClient:
    """A signed client from .env, or a key-less one for public market data."""
    demo = is_demo()
    if public_only:
        return BitgetClient(demo=demo)
    missing = missing_credentials()
    if missing:
        raise RuntimeError("Faltan variables en .env: " + ", ".join(missing))
    secret = _env("BITGET_SECRET_KEY")
    return BitgetClient(
        access_key=_env("BITGET_API_KEY", "BITGET_ACCESS_KEY"),
        passphrase=_env("BITGET_PASSPHRASE"),
        secret_key=secret or None,
        private_key=None if secret else _env("BITGET_PRIVATE_KEY_PATH", "BITGET_PRIVATE_KEY"),
        demo=demo,
    )
