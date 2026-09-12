#!/usr/bin/env python3
"""
Walk-forward validation — the honest version of scan_edges.

Single train/test splits let one lucky half carry the result. This retrains on a
rolling window and trades only the window that follows, then stitches every
out-of-sample stretch into one equity curve. That curve is what you would
actually have earned.

The grid is deliberately SMALL. scan_edges' significance check showed that
picking best-of-50 per asset finds lucky configs on pure noise 13.6 times out of
38. Fewer candidates means fewer lottery tickets.

    .venv/bin/python scripts/walkforward.py --interval 1H
    .venv/bin/python scripts/walkforward.py --interval 1H --shuffle   # null
"""
import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.scan_edges import load, evaluate, ema_trend, donchian, zscore_revert, FEES

# Small, theory-motivated grid: one classic config per family per speed.
GRID = [
    ("trend_ema", ema_trend,     dict(fast=12, slow=48,  band=0.0)),
    ("trend_ema", ema_trend,     dict(fast=12, slow=100, band=0.0)),
    ("trend_ema", ema_trend,     dict(fast=34, slow=150, band=0.0)),
    ("breakout",  donchian,      dict(lookback=20)),
    ("breakout",  donchian,      dict(lookback=60)),
    ("breakout",  donchian,      dict(lookback=150)),
    ("meanrev_z", zscore_revert, dict(lookback=48, entry=2.0)),
    ("meanrev_z", zscore_revert, dict(lookback=96, entry=2.5)),
]


def shuffle_df(df, rng):
    ret = df.close.pct_change().dropna().to_numpy(copy=True)
    rng.shuffle(ret)
    price = df.close.iloc[0] * np.cumprod(1 + ret)
    out = pd.DataFrame(index=df.index[1:])
    out["close"] = out["open"] = price
    rh = (df.high / df.close).to_numpy(copy=True)[1:]
    rl = (df.low / df.close).to_numpy(copy=True)[1:]
    rng.shuffle(rh); rng.shuffle(rl)
    out["high"] = price * rh
    out["low"]  = price * rl
    out["volume"] = df.volume.to_numpy()[1:]
    return out


def walk_forward(df, fee, bars_per_year, train_bars, test_bars):
    """Retrain each step; keep only the out-of-sample leg of each window."""
    oos_net, oos_turn, oos_gross = [], [], []
    start = 0
    while start + train_bars + test_bars <= len(df):
        tr = df.iloc[start:start + train_bars]
        te = df.iloc[start + train_bars:start + train_bars + test_bars]

        best, best_sh = None, -np.inf
        for _, build, params in GRID:
            r = evaluate(tr.close, build(tr, **params), fee, bars_per_year)
            if r and r["sharpe"] > best_sh:
                best_sh, best = r["sharpe"], (build, params)
        if best is None:
            start += test_bars
            continue

        build, params = best
        pos   = build(te, **params)
        ret   = te.close.pct_change().fillna(0.0)
        gross = pos.shift(1).fillna(0.0) * ret
        turn  = pos.diff().abs().fillna(0.0)
        oos_net.append(gross - turn * fee)
        oos_gross.append(gross)
        oos_turn.append(turn)
        start += test_bars

    if not oos_net:
        return None
    net   = pd.concat(oos_net)
    gross = pd.concat(oos_gross)
    turn  = pd.concat(oos_turn)
    n = int(turn.sum() / 2)
    if n < 15:
        return None
    sd = net.std()
    curve = (1 + net).cumprod()
    return dict(
        net=(1 + net).prod() - 1,
        sharpe=(net.mean() / sd * np.sqrt(bars_per_year)) if sd > 0 else 0.0,
        maxdd=(curve / curve.cummax() - 1).min(),
        trades=n,
        edge_bps=(gross.sum() - turn.sum() * fee) / n * 1e4,
        windows=len(oos_net),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", default="1H")
    ap.add_argument("--fee", choices=["maker", "taker"], default="maker")
    ap.add_argument("--train-days", type=int, default=90)
    ap.add_argument("--test-days", type=int, default=30)
    ap.add_argument("--shuffle", action="store_true", help="run the null instead")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    iv = args.interval
    fee = FEES[args.fee]
    bpy = {"1H": 8760, "4H": 2190, "1D": 365}[iv]
    per_day = {"1H": 24, "4H": 6, "1D": 1}[iv]
    train_bars, test_bars = args.train_days * per_day, args.test_days * per_day

    files = sorted(glob.glob(f"data/bitget/*_{iv}.csv"))
    rng = np.random.default_rng(args.seed)
    etiqueta = "DATOS BARAJADOS (null)" if args.shuffle else "DATOS REALES"
    print(f"\n{etiqueta} · {len(files)} activos · {iv} · fee {args.fee} · "
          f"train {args.train_days}d / test {args.test_days}d\n")

    ganadores = []
    for path in files:
        sym = os.path.basename(path).replace(f"_{iv}.csv", "")
        df = load(path)
        if args.shuffle:
            df = shuffle_df(df, rng)
        if len(df) < train_bars + test_bars:
            continue
        r = walk_forward(df, fee, bpy, train_bars, test_bars)
        if not r:
            continue
        if r["net"] > 0 and r["edge_bps"] > 0 and r["sharpe"] > 0.5:
            ganadores.append((sym, r))
            print(f"  ✅ {sym:<13} OOS {r['net']*100:+7.1f}%  Sharpe {r['sharpe']:5.2f}  "
                  f"maxDD {r['maxdd']*100:6.1f}%  {r['trades']:>3} trades  "
                  f"edge {r['edge_bps']:+6.1f}bps  ({r['windows']} ventanas)")

    print(f"\n{'═'*74}\n{len(ganadores)} activos con walk-forward positivo "
          f"(OOS+, edge>fees, Sharpe>0.5)")


if __name__ == "__main__":
    main()
