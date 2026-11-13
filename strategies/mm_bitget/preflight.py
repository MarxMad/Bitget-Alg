#!/usr/bin/env python3
"""
Everything that must be true before the bot places a real order, checked
against the live account rather than assumed.

    .venv/bin/python strategies/mm_bitget/preflight.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
from shared.bitget_client import unwrap
from shared.config import auth_method, client_from_env, is_demo, missing_credentials
from strategies.mm_bitget.core import MMConfig, size_from_equity

load_dotenv()
OK, WARN, FAIL = "✅", "⚠️ ", "❌"
fallos = []


def check(label, fn):
    try:
        estado, detalle = fn()
    except Exception as e:
        estado, detalle = FAIL, f"{type(e).__name__}: {e}"
    print(f"  {estado} {label:<28} {detalle}")
    if estado == FAIL:
        fallos.append(label)


def main():
    print("\n═══ PREFLIGHT ═══\n")

    faltan = missing_credentials()
    check("credenciales en .env", lambda: (
        (OK, f"completas · firma {auth_method()}" + (" · DEMO" if is_demo() else ""))
        if not faltan else (FAIL, "falta " + ", ".join(faltan))))

    if faltan:
        print("\n  Sin credenciales no puedo seguir.\n")
        return 1

    c = client_from_env()

    check("API pública", lambda: (
        (OK, f"XLM a {unwrap(client_from_env(public_only=True).get_tickers('XLMUSDT'))[0]['lastPrice']}")))

    def auth():
        r = c.get_positions()
        return ((OK, f"firma {auth_method()} válida") if r.get("code") == "00000"
                else (FAIL, f"{r.get('code')}: {r.get('msg')}"))
    check("autenticación", auth)

    def balance():
        r = c.get_account()
        if r.get("code") != "00000":
            return FAIL, f"{r.get('code')}: {r.get('msg')}"
        eq = float((r.get("data") or {}).get("accountEquity") or 0)
        if eq <= 0:
            return FAIL, "equity $0 — hay que fondear la cuenta"
        return OK, f"equity ${eq:.2f}"
    check("balance", balance)

    def kyc():
        # The only way to know an order would be accepted is to try one. This
        # quotes far from the market and post_only, so it cannot fill; it is
        # cancelled immediately whatever the outcome.
        r = c.place_order("XLMUSDT", "BUY", "LIMIT", "1",
                          price="0.001", time_in_force="POST_ONLY")
        code = r.get("code")
        if code == "00000":
            oid = (r.get("data") or {}).get("orderId")
            if oid:
                c.cancel_order("XLMUSDT", order_id=oid)
            return OK, "la cuenta puede colocar órdenes"
        if code == "40035":
            return FAIL, "KYC pendiente — ninguna orden será aceptada"
        if code in ("40762", "22002", "45110"):
            return WARN, f"{code}: {r.get('msg')} (saldo/tamaño, no permisos)"
        return FAIL, f"{code}: {r.get('msg')}"
    check("permiso de trading", kyc)

    def sizing():
        r = c.get_account()
        eq = float((r.get("data") or {}).get("accountEquity") or 0)
        cfg = MMConfig()
        s = size_from_equity(eq, len(cfg.universe), cfg.risk_budget,
                             cfg.max_gross_leverage)
        if not s.ok:
            return WARN, s.reason
        return OK, (f"${s.order_usdt:.2f} × {s.symbols} símbolos · "
                    f"${s.volume_per_day:,.0f}/día · σ {s.sigma_pct*100:.1f}%")
    check("dimensionamiento", sizing)

    def ip():
        return WARN, "sin IP bindeada (Bitget puede degradar la key a los 90 días)"
    check("IP de la API key", ip)

    print()
    if fallos:
        print(f"  {len(fallos)} bloqueo(s): {', '.join(fallos)}")
        print("  El bot puede correr en PAPEL, pero no operará real hasta resolverlos.\n")
        return 1
    print("  Todo listo para operar.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
