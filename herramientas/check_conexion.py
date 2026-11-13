#!/usr/bin/env python3
"""
Revisa que tu entorno y tu API key de Bitget funcionen. Es lo primero que se
corre en el taller.

    python herramientas/check_conexion.py

1. Datos públicos (no necesita llaves): precio, libro, velas, contrato.
2. Datos privados (con tu .env): firma, posiciones, órdenes y saldo.

No coloca órdenes. Solo lee.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from shared.bitget_client import unwrap
from shared.config import auth_method, client_from_env, is_demo, missing_credentials

load_dotenv()

SYMBOL = os.getenv("BITGET_TEST_SYMBOL", "BTCUSDT")

# Códigos de error frecuentes y qué hacer con cada uno.
AYUDA = {
    "40006": "API key inválida o de otro entorno. ¿Usas una Demo API key con BITGET_DEMO=1?",
    "40009": "Firma inválida: revisa BITGET_SECRET_KEY (sin espacios ni comillas de más).",
    "40011": "Passphrase incorrecta (BITGET_PASSPHRASE). No se puede recuperar: crea otra key.",
    "40012": "API key o passphrase incorrecta.",
    "40014": "La key no tiene permiso para esto: activa lectura y trading al crearla.",
    "40035": "Falta completar el KYC (verificación de identidad) en tu cuenta.",
    "40037": "La API key no existe. ¿La borraste o la copiaste incompleta?",
    "40085": "Tu cuenta está en modo clásico; este repo usa la API v3 (Cuenta Unificada).",
}


def show(label, fn, extract=None):
    try:
        resp = fn()
    except Exception as e:
        print(f"  ❌ {label:<20} {type(e).__name__}: {str(e)[:70]}")
        return False
    code = str(resp.get("code"))
    if code == "00000":
        try:
            detail = extract(resp) if extract else ""
        except Exception as e:
            detail = f"(OK, formato inesperado: {e})"
        print(f"  ✅ {label:<20} {detail}")
        return True
    print(f"  ❌ {label:<20} code={code} msg={resp.get('msg')}")
    if code in AYUDA:
        print(f"     → {AYUDA[code]}")
    return False


def main():
    entorno = "DEMO (fondos simulados)" if is_demo() else "REAL"
    print(f"\nEntorno: {entorno}   ·   símbolo de prueba: {SYMBOL}")

    print("\n═══ 1. PÚBLICO: sin llaves ═══")
    pub = client_from_env(public_only=True)
    ok_pub = show("precio", lambda: pub.get_tickers(SYMBOL),
                  lambda r: f"último = {unwrap(r)[0].get('lastPrice')}")
    show("libro de órdenes", lambda: pub.get_depth(SYMBOL, 5),
         lambda r: f"bid {r['data']['b'][0][0]} / ask {r['data']['a'][0][0]}")
    show("velas 1m", lambda: pub.get_kline(SYMBOL, "1m", 5),
         lambda r: f"{len(unwrap(r))} velas, cierre = {unwrap(r)[-1][4]}")
    show("contrato", lambda: pub.get_instruments(SYMBOL),
         lambda r: (f"mín {unwrap(r)[0].get('minOrderAmount')} USDT · "
                    f"apalancamiento máx {unwrap(r)[0].get('maxLeverage')}x"))
    if not ok_pub:
        print("\n  Sin datos públicos: revisa tu internet o el símbolo (BITGET_TEST_SYMBOL).")

    print("\n═══ 2. PRIVADO: con tu .env ═══")
    missing = missing_credentials()
    if missing:
        print(f"  ⏭  Saltado. Falta en .env: {', '.join(missing)}")
        print("     Sigue guias/02-api-key-demo.md para crear tu key y llenar el .env.\n")
        return 1

    try:
        cli = client_from_env()
    except Exception as e:
        print(f"  ❌ No pude crear el cliente: {e}\n")
        return 1

    print(f"  Firma: {auth_method()}")
    auth = show("posiciones", lambda: cli.get_positions(),
                lambda r: f"{len(unwrap(r))} abiertas")
    show("órdenes pendientes", lambda: cli.get_pending_orders(),
         lambda r: f"{len(unwrap(r))} pendientes")
    show("saldo", lambda: cli.get_account(),
         lambda r: f"equity = {r['data'].get('accountEquity')} USDT")

    print()
    if auth:
        print("  🎉 Tu API key funciona. Ya puedes seguir con la guía 03.\n")
        return 0
    print("  ⚠️  La autenticación falla. Lee el mensaje de arriba (→) y la guía 06.\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
