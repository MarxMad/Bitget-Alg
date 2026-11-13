#!/usr/bin/env python3
"""
Replay a fixed-spread market maker against real Bitget 1m data.

A fixed-spread MM quotes buy at mid*(1 - spread_pct/2) and sell at
mid*(1 + spread_pct/2). With the default spread_pct=0.0004 that captures 0.04%
per completed round trip — exactly the 0.02% maker fee paid on each of the two
fills. The design is breakeven by construction, so whatever it actually earns is
the mean-reversion edge of buying 0.02% dips and selling 0.02% rips, nothing
else. This measures that edge.

    python strategies/mm_bitget/replay_fixed_spread.py --symbol XLMUSDT --spread 0.0004
"""
import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from herramientas.scan_edges import load

MAKER = 0.0002


def simulate(df, spread_pct, max_inventory, order_usd):
    half = spread_pct / 2
    inv = 0.0            # units held (signed)
    cash = 0.0
    fees = 0.0
    volume = 0.0
    fills_buy = fills_sell = 0
    both_sides = 0
    equity = []

    closes = df.close.to_numpy()
    highs, lows = df.high.to_numpy(), df.low.to_numpy()

    for i in range(1, len(df)):
        mid = closes[i - 1]
        bid_px, ask_px = mid * (1 - half), mid * (1 + half)
        qty = order_usd / mid

        hit_buy  = lows[i]  <= bid_px and inv <  max_inventory * qty
        hit_sell = highs[i] >= ask_px and inv > -max_inventory * qty

        if hit_buy:
            cash -= bid_px * qty; inv += qty
            fees += bid_px * qty * MAKER; volume += bid_px * qty
            fills_buy += 1
        if hit_sell:
            cash += ask_px * qty; inv -= qty
            fees += ask_px * qty * MAKER; volume += ask_px * qty
            fills_sell += 1
        if hit_buy and hit_sell:
            both_sides += 1

        equity.append(cash + inv * closes[i] - fees)

    eq = pd.Series(equity, index=df.index[1:])
    return dict(pnl=eq.iloc[-1], fees=fees, volume=volume,
                fills=fills_buy + fills_sell, both=both_sides,
                buys=fills_buy, sells=fills_sell,
                final_inv_usd=inv * closes[-1], curve=eq)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="XLMUSDT")
    ap.add_argument("--spread", type=float, default=0.0004, help="spread_pct del bot")
    ap.add_argument("--order-usd", type=float, default=10.0)
    ap.add_argument("--max-inventory", type=float, default=5.0, help="en múltiplos de order qty")
    args = ap.parse_args()

    path = f"data/bitget/{args.symbol}_1m.csv"
    if not os.path.exists(path):
        sys.exit(f"falta {path}")
    df = load(path)
    dias = (df.index[-1] - df.index[0]).total_seconds() / 86400

    print(f"\n{args.symbol} · {len(df):,} velas 1m · {dias:.1f} días · "
          f"orden ${args.order_usd} · spread {args.spread*100:.3f}%\n")
    print(f"{'spread bot':>11}{'fills':>9}{'ambos lados':>13}{'volumen':>12}"
          f"{'fees':>9}{'PnL neto':>11}{'% del vol':>11}")
    print("─" * 78)

    for sp in (args.spread, args.spread * 2, args.spread * 5, args.spread * 10):
        r = simulate(df, sp, args.max_inventory, args.order_usd)
        pct = r["pnl"] / r["volume"] * 100 if r["volume"] else 0
        print(f"{sp*100:>10.3f}%{r['fills']:>9,}{r['both']:>13,}"
              f"${r['volume']:>11,.0f}${r['fees']:>8,.2f}${r['pnl']:>10,.2f}{pct:>10.4f}%")

    print("─" * 78)
    r = simulate(df, args.spread, args.max_inventory, args.order_usd)
    anual = r["volume"] / dias * 365
    print(f"\nCon el spread por defecto del bot ({args.spread*100:.3f}%):")
    print(f"  compras {r['buys']:,} · ventas {r['sells']:,} · "
          f"bares con ambos lados {r['both']:,}")
    print(f"  inventario final sin cerrar: ${r['final_inv_usd']:+,.2f}")
    print(f"  volumen anualizado con orden de ${args.order_usd}: ${anual:,.0f}/año")
    print(f"  PnL neto: ${r['pnl']:+,.2f} en {dias:.0f} días")


if __name__ == "__main__":
    main()
