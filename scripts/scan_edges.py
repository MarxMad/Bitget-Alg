#!/usr/bin/env python3
"""
Systematic edge scan over Bitget data.

The only question this answers: does any (asset, strategy, params) combination
produce gross edge per trade LARGER than the fee it pays per trade — on data it
was not fitted to?

    .venv/bin/python scripts/scan_edges.py --interval 1h
    .venv/bin/python scripts/scan_edges.py --interval 1h --fee maker

Discipline: params are ranked on TRAIN, reported on TEST. A config counts as
robust only if it is positive on BOTH halves. Ranking on train alone is how you
pick overfitted garbage — the previous Bitunix sweep showed configs going
+144% train / -31% test.
"""
import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd

# Bitget USDT-M perpetual fees, read off /api/v3/market/instruments.
FEES = {"maker": 0.0002, "taker": 0.0006}


def load(path):
    df = pd.read_csv(path)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    df = df.sort_values("ts").drop_duplicates("ts").set_index("ts")
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def evaluate(close, pos, fee, bars_per_year):
    """Net returns after fees, plus the per-trade economics that decide it."""
    ret = close.pct_change().fillna(0.0)
    # position is decided on bar t and earns bar t+1's return
    gross = pos.shift(1).fillna(0.0) * ret
    turn  = pos.diff().abs().fillna(0.0)
    cost  = turn * fee
    net   = gross - cost

    n_trades = int(turn.sum() / 2)
    if n_trades < 10:
        return None

    eq = (1 + net).prod() - 1
    sd = net.std()
    sharpe = (net.mean() / sd * np.sqrt(bars_per_year)) if sd > 0 else 0.0
    curve = (1 + net).cumprod()
    maxdd = (curve / curve.cummax() - 1).min()

    # The decisive comparison, per round trip, in basis points.
    gross_bps = gross.sum() / n_trades * 1e4
    fee_bps   = cost.sum() / n_trades * 1e4
    return dict(net=eq, sharpe=sharpe, maxdd=maxdd, trades=n_trades,
                gross_bps=gross_bps, fee_bps=fee_bps, edge_bps=gross_bps - fee_bps)


# ─── strategy families (each returns a position series in [-1, 1]) ────────────

def ema_trend(df, fast, slow, band=0.0):
    f = df.close.ewm(span=fast).mean()
    s = df.close.ewm(span=slow).mean()
    sep = (f - s) / s
    return pd.Series(np.where(sep > band, 1.0, np.where(sep < -band, -1.0, 0.0)), index=df.index)


def donchian(df, lookback, exit_frac=0.5):
    hi = df.high.rolling(lookback).max().shift(1)
    lo = df.low.rolling(lookback).min().shift(1)
    raw = pd.Series(np.where(df.close > hi, 1.0, np.where(df.close < lo, -1.0, np.nan)), index=df.index)
    return raw.ffill().fillna(0.0)


def zscore_revert(df, lookback, entry):
    m = df.close.rolling(lookback).mean()
    s = df.close.rolling(lookback).std()
    z = (df.close - m) / s
    return pd.Series(np.where(z > entry, -1.0, np.where(z < -entry, 1.0, 0.0)), index=df.index)


FAMILIES = {
    "trend_ema":  [dict(fast=f, slow=s, band=b)
                   for f in (8, 12, 20, 34) for s in (48, 100, 150) for b in (0.0, 0.01)],
    "breakout":   [dict(lookback=l) for l in (20, 40, 60, 100, 150)],
    "meanrev_z":  [dict(lookback=l, entry=e) for l in (24, 48, 96) for e in (1.5, 2.0, 2.5)],
}
BUILDERS = {"trend_ema": ema_trend, "breakout": donchian, "meanrev_z": zscore_revert}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", default="1H")
    ap.add_argument("--fee", choices=["maker", "taker"], default="maker")
    ap.add_argument("--data-dir", default="data/bitget")
    ap.add_argument("--min-trades", type=int, default=20)
    args = ap.parse_args()

    iv = args.interval if args.interval in ("1m","5m","15m","30m","1H","4H","1D") \
         else args.interval[:-1] + args.interval[-1].upper()
    fee = FEES[args.fee]
    bars_per_year = {"1m": 525600, "5m": 105120, "15m": 35040, "30m": 17520,
                     "1H": 8760, "4H": 2190, "1D": 365}[iv]

    files = sorted(glob.glob(os.path.join(args.data_dir, f"*_{iv}.csv")))
    if not files:
        sys.exit(f"no hay CSVs en {args.data_dir} con intervalo {iv}")

    print(f"\n{len(files)} activos · {iv} · fee {args.fee} {fee*100:.3f}%/lado "
          f"({fee*2*1e4:.0f} bps por vuelta)\n")

    robustos = []
    for path in files:
        sym = os.path.basename(path).replace(f"_{iv}.csv", "")
        df = load(path)
        if len(df) < 400:
            continue
        cut = int(len(df) * 0.66)
        tr, te = df.iloc[:cut], df.iloc[cut:]

        mejor = None
        for fam, grid in FAMILIES.items():
            build = BUILDERS[fam]
            for params in grid:
                r_tr = evaluate(tr.close, build(tr, **params), fee, bars_per_year)
                if not r_tr or r_tr["trades"] < args.min_trades:
                    continue
                # rank on TRAIN only
                if mejor is None or r_tr["sharpe"] > mejor[0]["sharpe"]:
                    r_te = evaluate(te.close, build(te, **params), fee, bars_per_year)
                    if r_te:
                        mejor = (r_tr, r_te, fam, params)

        if not mejor:
            continue
        r_tr, r_te, fam, params = mejor
        ok = r_tr["net"] > 0 and r_te["net"] > 0 and r_te["edge_bps"] > 0
        if ok:
            robustos.append((sym, fam, params, r_tr, r_te))
        print(f"  {sym:<13} {fam:<11} train {r_tr['net']*100:+7.1f}%  "
              f"test {r_te['net']*100:+7.1f}%  edge/trade(test) {r_te['edge_bps']:+7.1f}bps  "
              f"{'✅' if ok else ''}")

    print("\n" + "═"*78)
    if not robustos:
        print("❌ NINGÚN activo pasó el filtro (positivo en train Y test, edge > fees en test).")
        print("   Es el resultado más común y el más honesto. No hay edge que desplegar.")
        return
    print(f"✅ {len(robustos)} de {len(files)} pasaron train+ / test+ / edge>fees\n")
    print(f"{'activo':<13}{'familia':<12}{'test net':>10}{'Sharpe':>9}{'maxDD':>9}{'trades':>8}{'edge/trade':>12}")
    print("─"*78)
    for sym, fam, params, r_tr, r_te in sorted(robustos, key=lambda x: -x[4]["sharpe"]):
        print(f"{sym:<13}{fam:<12}{r_te['net']*100:>9.1f}%{r_te['sharpe']:>9.2f}"
              f"{r_te['maxdd']*100:>8.1f}%{r_te['trades']:>8}{r_te['edge_bps']:>10.1f}bps")
        print(f"{'':13}{str(params)}")


if __name__ == "__main__":
    main()
