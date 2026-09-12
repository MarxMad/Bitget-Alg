#!/usr/bin/env python3
"""
Backtest the market maker by replaying the BOT'S OWN quoting functions.

This imports realized_vol, quote_prices, sides_allowed and needs_reprice from
core.py rather than reimplementing them. A backtest that reimplements the
strategy validates a second piece of code that nobody runs — the two drift, and
the numbers stop describing the bot.

Fill model, and where it is optimistic:
  * a resting bid fills when the bar's low trades at or through it
  * the requote throttle is honoured, so stale quotes stay stale exactly as live
  * fills assume queue priority at that price — true for quotes resting outside
    the touch (price traded through them), optimistic at the touch
  * both sides may fill within one bar, which flatters tight widths

    python -m strategies.mm_bitget.backtest --symbols SOLUSDT,BTCUSDT
    python -m strategies.mm_bitget.backtest --sweep
"""
import argparse
import glob
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.scan_edges import load
from strategies.mm_bitget.core import (
    MMConfig, realized_vol, quote_prices, sides_allowed, needs_reprice,
)

MAKER = 0.0002


def replay(df, cfg: MMConfig):
    """One symbol, bar by bar, using the live quoting functions verbatim."""
    closes = df.close.to_numpy()
    highs, lows = df.high.to_numpy(), df.low.to_numpy()
    n = len(df)

    inv_units = 0.0
    cash = fees = volume = 0.0
    fills = buys = sells = 0
    quote = None
    requotes = 0
    peak_inv = 0.0
    daily = {}
    prev_equity = 0.0
    spread_pnl = 0.0        # half-spread earned on fills, before inventory drift

    # realized_vol needs window+1 closes to form `window` returns — slicing
    # exactly vol_window silently yields None on every bar and zero fills.
    for i in range(cfg.vol_window + 1, n):
        window = list(closes[i - cfg.vol_window - 1:i])
        vol = realized_vol(window, cfg.vol_window)
        if vol is None:
            continue
        mid = closes[i - 1]
        inv_usd = inv_units * mid

        pair = quote_prices(mid, vol, inv_usd, cfg)
        if pair is None:
            continue
        if needs_reprice(quote, pair, vol, mid, cfg):
            quote = pair
            requotes += 1
        bid, ask = quote

        may_bid, may_ask = sides_allowed(inv_usd, cfg)
        qty = cfg.order_usdt / mid

        day = df.index[i].date()

        bid_fill_pnl = ask_fill_pnl = 0.0
        if may_bid and lows[i] <= bid:
            cash -= bid * qty; inv_units += qty
            fees += bid * qty * MAKER; volume += bid * qty
            fills += 1; buys += 1
            bid_fill_pnl = (mid - bid) * qty - bid * qty * MAKER
        if may_ask and highs[i] >= ask:
            cash += ask * qty; inv_units -= qty
            fees += ask * qty * MAKER; volume += ask * qty
            fills += 1; sells += 1
            ask_fill_pnl = (ask - mid) * qty - ask * qty * MAKER

        # Mark to market against the PREVIOUS bar, not against this bar before
        # the fills: anchoring inside the bar counts only fill P&L and silently
        # drops the revaluation of inventory already held, which is most of it.
        equity = cash + inv_units * closes[i] - fees
        daily[day] = daily.get(day, 0.0) + (equity - prev_equity)
        prev_equity = equity
        spread_pnl += (bid_fill_pnl + ask_fill_pnl)
        peak_inv = max(peak_inv, abs(inv_units * closes[i]))

    pnl = cash + inv_units * closes[-1] - fees
    return dict(pnl=pnl, spread_pnl=spread_pnl,
                inventory_pnl=pnl - spread_pnl,
                volume=volume, fees=fees, fills=fills,
                buys=buys, sells=sells, requotes=requotes,
                peak_inventory=peak_inv, daily=daily,
                open_inventory=inv_units * closes[-1])


def summarise(label, results, dias):
    pnl = sum(r["pnl"] for r in results)
    vol = sum(r["volume"] for r in results)
    fills = sum(r["fills"] for r in results)
    buys = sum(r["buys"] for r in results)
    sells = sum(r["sells"] for r in results)
    peak = sum(r["peak_inventory"] for r in results)

    combinado = {}
    for r in results:
        for d, v in r["daily"].items():
            combinado[d] = combinado.get(d, 0.0) + v
    dd = sorted(combinado.values())
    pos = sum(1 for v in dd if v > 0) / len(dd) * 100 if dd else 0
    media = st.mean(dd) if dd else 0
    sd = st.pstdev(dd) if len(dd) > 1 else 0
    err = sd / (len(dd) ** 0.5) if dd else 0

    print(f"\n── {label} ──")
    sp = sum(r["spread_pnl"] for r in results)
    iv = sum(r["inventory_pnl"] for r in results)
    print(f"  PnL total        ${pnl:+.2f}   ({pnl/vol*100 if vol else 0:+.4f}% del volumen)")
    print(f"    ├─ spread neto ${sp:+.2f}   ← lo que el market making gana o pierde")
    print(f"    └─ inventario  ${iv:+.2f}   ← deriva direccional, NO es edge")
    print(f"  volumen          ${vol:,.0f}  ·  ${vol/dias:,.0f}/día  ·  ${vol/dias*365:,.0f}/año")
    print(f"  comisiones       ${sum(r['fees'] for r in results):,.2f}")
    print(f"  fills            {fills:,}  ({buys:,} compras / {sells:,} ventas)")
    print(f"  inventario pico  ${peak:,.2f}")
    print(f"  PnL diario       ${media:+.3f} ± {err:.3f} (error estándar) · σ ${sd:.2f}")
    print(f"  días positivos   {pos:.0f}% de {len(dd)}")
    if dd:
        print(f"  peor / mejor día ${dd[0]:+.2f} / ${dd[-1]:+.2f}")
    sig = abs(media) > 2 * err if err else False
    print(f"  → {'✅ distinto de cero' if sig and media>0 else '❌ pierde' if sig else '≈ breakeven (no distinguible de cero)'}")
    return media, vol / dias


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="")
    ap.add_argument("--order-usdt", type=float, default=10.0)
    ap.add_argument("--vol-multiple", type=float, default=2.5)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--holdout", action="store_true",
                    help="elegir el ancho en la 1a mitad y reportar la 2a")
    args = ap.parse_args()

    if args.symbols:
        syms = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        syms = sorted(os.path.basename(p).replace("_1m.csv", "")
                      for p in glob.glob("data/bitget/*_1m.csv"))
    datos = {s: load(f"data/bitget/{s}_1m.csv") for s in syms
             if os.path.exists(f"data/bitget/{s}_1m.csv")}
    if not datos:
        sys.exit("no hay CSVs de 1m en data/bitget/")
    dias = st.mean([(d.index[-1] - d.index[0]).total_seconds() / 86400
                    for d in datos.values()])
    print(f"\n{len(datos)} símbolos · {dias:.1f} días · órdenes ${args.order_usdt} "
          f"· réplica de las funciones reales del bot")

    if args.sweep:
        print(f"\n{'ancho':>7}{'PnL/día':>11}{'err.est.':>10}{'días +':>9}"
              f"{'vol/día':>12}{'vol/año':>14}")
        print("─" * 65)
        for vm in (1.5, 2.0, 2.5, 3.0, 3.5, 4.0):
            cfg = MMConfig(vol_multiple=vm, order_usdt=args.order_usdt)
            res = [replay(d, cfg) for d in datos.values()]
            comb = {}
            for r in res:
                for d, v in r["daily"].items():
                    comb[d] = comb.get(d, 0.0) + v
            vals = list(comb.values())
            m = st.mean(vals); e = st.pstdev(vals) / (len(vals) ** .5)
            p = sum(1 for v in vals if v > 0) / len(vals) * 100
            vd = sum(r["volume"] for r in res) / dias
            marca = "✅" if m > 2 * e else "❌" if m < -2 * e else "≈"
            print(f"{vm:>6.1f}x{m:>+10.3f}${e:>9.3f}{p:>8.0f}%"
                  f"${vd:>11,.0f}${vd*365:>13,.0f} {marca}")
        print("─" * 65)
        print("  ✅ ganancia real · ≈ breakeven (lo que buscamos) · ❌ pierde")
        return

    if args.holdout:
        for etiqueta, corte in (("ENTRENAMIENTO (1a mitad)", "tr"), ("PRUEBA (2a mitad)", "te")):
            res = []
            for d in datos.values():
                half = len(d) // 2
                res.append(replay(d.iloc[:half] if corte == "tr" else d.iloc[half:],
                                  MMConfig(vol_multiple=args.vol_multiple,
                                           order_usdt=args.order_usdt)))
            summarise(f"{etiqueta} · ancho {args.vol_multiple}x", res, dias / 2)
        return

    cfg = MMConfig(vol_multiple=args.vol_multiple, order_usdt=args.order_usdt)
    summarise(f"ancho {args.vol_multiple}x · {', '.join(datos)}",
              [replay(d, cfg) for d in datos.values()], dias)


if __name__ == "__main__":
    main()
