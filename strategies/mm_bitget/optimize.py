#!/usr/bin/env python3
"""
Find the market-maker configuration that maximises volume subject to NOT losing
money, using real Bitget 1m data.

The old design quoted a fixed mid±0.02% regardless of the book. On BTC, whose
spread is 0.0001%, that rests far outside the touch and only fills when price
runs through it — buying dips and selling rips, which is mean reversion with
negative expectancy, not spread capture.

Three changes are tested here:
  * spread width as a multiple of the asset's own 1m volatility, instead of a
    constant, so quotes sit where the asset actually trades
  * inventory skew: shift both quotes against the position so the book pulls
    itself flat instead of accumulating one-sided risk
  * a hard inventory cap that stops quoting the side that would add to it

Params are chosen on the FIRST half of the data and scored on the SECOND.
Optimising and reporting on the same window is how the previous sweep produced
11 winners that a coin flip beat.
"""
import argparse
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from herramientas.scan_edges import load

MAKER = 0.0002


def run(df, vol_mult, skew_mult, max_inv_mult, order_usd):
    """Returns (pnl, volume, fills, max_abs_inventory_usd)."""
    closes = df.close.to_numpy()
    highs, lows = df.high.to_numpy(), df.low.to_numpy()

    # Rolling 1m volatility sets the quote width: wide where the asset moves.
    rets = [0.0] + [abs(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes))]
    win = 60
    inv_units = 0.0
    cash = 0.0
    fees = 0.0
    volume = 0.0
    fills = 0
    peak_inv = 0.0

    for i in range(win, len(df)):
        vol = sum(rets[i - win:i]) / win
        if vol <= 0:
            continue
        mid = closes[i - 1]
        qty = order_usd / mid
        half = mid * vol * vol_mult

        inv_usd = inv_units * mid
        cap = max_inv_mult * order_usd
        # Skew both quotes against the inventory: long inventory pushes the
        # pair down, making the ask easier to hit and the bid harder.
        skew = (inv_usd / cap) * half * skew_mult if cap else 0.0

        bid_px = mid - half - skew
        ask_px = mid + half - skew
        if bid_px >= ask_px:        # never let our own quotes cross
            continue

        hit_buy  = lows[i]  <= bid_px and inv_usd <  cap
        hit_sell = highs[i] >= ask_px and inv_usd > -cap

        if hit_buy:
            cash -= bid_px * qty; inv_units += qty
            fees += bid_px * qty * MAKER; volume += bid_px * qty; fills += 1
        if hit_sell:
            cash += ask_px * qty; inv_units -= qty
            fees += ask_px * qty * MAKER; volume += ask_px * qty; fills += 1
        peak_inv = max(peak_inv, abs(inv_units * mid))

    pnl = cash + inv_units * closes[-1] - fees
    return pnl, volume, fills, peak_inv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="XLMUSDT,ETHUSDT,BTCUSDT,SOLUSDT")
    ap.add_argument("--order-usd", type=float, default=10.0)
    args = ap.parse_args()

    VOL_MULTS  = [0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 12.0]
    SKEWS      = [0.0, 0.5, 1.0]
    INV_CAPS   = [3, 5, 10]

    for sym in args.symbols.split(","):
        path = f"data/bitget/{sym}_1m.csv"
        if not os.path.exists(path):
            print(f"{sym}: falta {path}"); continue
        df = load(path)
        cut = len(df) // 2
        tr, te = df.iloc[:cut], df.iloc[cut:]
        dias_te = (te.index[-1] - te.index[0]).total_seconds() / 86400

        # Choose on train: most volume among configs that do not lose money.
        mejor = None
        for vm, sk, cap in itertools.product(VOL_MULTS, SKEWS, INV_CAPS):
            pnl, vol, fills, peak = run(tr, vm, sk, cap, args.order_usd)
            if pnl >= 0 and fills > 50:
                if mejor is None or vol > mejor[1]:
                    mejor = (pnl, vol, fills, peak, vm, sk, cap)

        print(f"\n═══ {sym} ═══")
        if not mejor:
            print("  ninguna configuración quedó en positivo en la mitad de entrenamiento")
            continue
        _, _, _, _, vm, sk, cap = mejor
        pnl, vol, fills, peak = run(te, vm, sk, cap, args.order_usd)
        anual = vol / dias_te * 365
        print(f"  elegida en train : ancho {vm}x vol · skew {sk} · cap {cap} órdenes")
        print(f"  EN TEST ({dias_te:.1f}d) : PnL ${pnl:+.2f} · volumen ${vol:,.0f} · "
              f"{fills:,} fills · inventario máx ${peak:,.0f}")
        print(f"  → {'✅ positivo' if pnl >= 0 else '❌ negativo'} · "
              f"{pnl/vol*100 if vol else 0:+.4f}% del volumen")
        print(f"  → volumen anualizado con órdenes de ${args.order_usd}: ${anual:,.0f}")


if __name__ == "__main__":
    main()
