#!/usr/bin/env python3
"""
Connectivity + credential check for Bitget (Unified / v3 API).
Read-only — places no orders and cancels nothing real.

Run:  .venv/bin/python scripts/test_bitget.py

Needs in .env:  BITGET_ACCESS_KEY, BITGET_PASSPHRASE, BITGET_PRIVATE_KEY_PATH
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from shared.bitget_client import BitgetClient, unwrap

load_dotenv()

SYMBOL = os.getenv("BITGET_TEST_SYMBOL", "XLMUSDT")


def show(label, fn, extract=None):
    try:
        resp = fn()
    except Exception as e:
        print(f"  ❌ {label:<22} {type(e).__name__}: {str(e)[:60]}")
        return False
    if resp.get("code") == "00000":
        try:
            detail = extract(resp) if extract else ""
        except Exception as e:
            detail = f"(OK, formato inesperado: {e})"
        print(f"  ✅ {label:<22} {detail}")
        return True
    print(f"  ❌ {label:<22} code={resp.get('code')} msg={resp.get('msg')}")
    return False


def main():
    print(f"\n═══ PÚBLICO — sin credenciales ({SYMBOL}) ═══")
    pub = BitgetClient()
    show("ticker", lambda: pub.get_tickers(SYMBOL),
         lambda r: f"último = {unwrap(r)[0].get('lastPrice')}")
    show("profundidad", lambda: pub.get_depth(SYMBOL, 5),
         lambda r: f"bid {r['data']['b'][0][0]} / ask {r['data']['a'][0][0]}")
    show("velas 1m", lambda: pub.get_kline(SYMBOL, "1m", 5),
         lambda r: f"{len(unwrap(r))} velas, close = {unwrap(r)[-1][4]}")
    show("specs contrato", lambda: pub.get_instruments(SYMBOL),
         lambda r: (f"mín {unwrap(r)[0].get('minOrderAmount')} USDT / "
                    f"lev máx {unwrap(r)[0].get('maxLeverage')}x / "
                    f"maker {float(unwrap(r)[0].get('makerFeeRate'))*100:.3f}%"))
    show("funding rate", lambda: pub.get_funding_rate(SYMBOL),
         lambda r: f"{float(unwrap(r)[0]['fundingRate'])*100:.4f}%")

    access  = os.getenv("BITGET_ACCESS_KEY", "")
    passph  = os.getenv("BITGET_PASSPHRASE", "")
    keypath = os.getenv("BITGET_PRIVATE_KEY_PATH", "")

    print("\n═══ PRIVADO — con tus credenciales ═══")
    missing = [n for n, v in [("BITGET_ACCESS_KEY", access),
                              ("BITGET_PASSPHRASE", passph),
                              ("BITGET_PRIVATE_KEY_PATH", keypath)] if not v]
    if missing:
        print(f"  ⏭  Saltado. Falta en .env: {', '.join(missing)}")
        return
    if not os.path.exists(keypath):
        print(f"  ❌ No existe la llave privada: {keypath}")
        return

    cli = BitgetClient(access_key=access, passphrase=passph, private_key=keypath)
    auth = show("posiciones", lambda: cli.get_positions(),
                lambda r: f"{len(unwrap(r))} abiertas")
    show("órdenes pendientes", lambda: cli.get_pending_orders(),
         lambda r: f"{len(unwrap(r))} pendientes")
    show("balance", lambda: cli.get_account(),
         lambda r: (f"equity = {r['data'].get('accountEquity')} USDT"
                    f"  ({len(r['data'].get('assets') or [])} monedas con saldo)"))

    print()
    if auth:
        print("  🎉 Firma RSA válida. La cuenta responde.")
    else:
        print("  ⚠️  Autenticación fallando — revisa el código de error.")


if __name__ == "__main__":
    main()
