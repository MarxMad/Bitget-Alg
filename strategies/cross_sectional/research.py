#!/usr/bin/env python3
"""
Cross-sectional momentum across the Bitget universe.

Structurally different from everything in scan_edges/walkforward: it never
predicts one asset's direction. It ranks the whole universe by trailing return,
goes long the strongest K and short the weakest K, and rebalances. The bet is on
relative persistence, which survives in equities and futures far better than
single-asset timing.

Runs the null the same way — each asset's returns shuffled independently, which
destroys cross-sectional structure while keeping every marginal distribution.

    .venv/bin/python strategies/cross_sectional/research.py
    .venv/bin/python strategies/cross_sectional/research.py --shuffle --seed 3
"""
import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from herramientas.scan_edges import load, FEES


# Coins that were already liquid majors a year ago. Selecting the universe by
# TODAY's turnover is lookahead: an asset is in that list partly because it
# pumped, and momentum over a pumped-into-existence universe backtests
# beautifully for reasons that cannot be traded.
MAJORS = ["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","DOGEUSDT",
          "ADAUSDT","LINKUSDT","XLMUSDT","UNIUSDT","NEARUSDT","SUIUSDT"]


def panel(interval, shuffle, seed, only=None):
    rng = np.random.default_rng(seed)
    cols = {}
    for path in sorted(glob.glob(f"data/bitget/*_{interval}.csv")):
        sym = os.path.basename(path).replace(f"_{interval}.csv", "")
        if only and sym not in only:
            continue
        df = load(path)
        if len(df) < 500:
            continue
        s = df.close
        if shuffle:
            r = s.pct_change().dropna().to_numpy(copy=True)
            rng.shuffle(r)
            s = pd.Series(s.iloc[0] * np.cumprod(1 + r), index=s.index[1:])
        cols[sym] = s
    return pd.DataFrame(cols).dropna(how="all").ffill()


def backtest(px, lookback, hold, k, fee):
    ret = px.pct_change()
    mom = px.pct_change(lookback)

    weights = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    for i in range(lookback, len(px), hold):
        row = mom.iloc[i].dropna()
        if len(row) < 2 * k:
            continue
        ranked = row.sort_values()
        shorts, longs = ranked.index[:k], ranked.index[-k:]
        w = pd.Series(0.0, index=px.columns)
        w[longs]  = 1.0 / k
        w[shorts] = -1.0 / k
        weights.iloc[i:i + hold] = w.values

    gross = (weights.shift(1) * ret).sum(axis=1).fillna(0.0)
    turn  = weights.diff().abs().sum(axis=1).fillna(0.0)
    net   = gross - turn * fee
    n_reb = int((turn > 0).sum())
    if n_reb < 5:
        return None
    sd = net.std()
    curve = (1 + net).cumprod()
    bpy = {"1H": 8760, "4H": 2190, "1D": 365}["1H"]
    return dict(net=(1 + net).prod() - 1,
                sharpe=(net.mean() / sd * np.sqrt(bpy)) if sd > 0 else 0.0,
                maxdd=(curve / curve.cummax() - 1).min(),
                fees=turn.sum() * fee,
                gross=gross.sum(),
                rebalances=n_reb)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", default="1H")
    ap.add_argument("--shuffle", action="store_true")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--majors", action="store_true", help="survivorship-free universe")
    args = ap.parse_args()
    fee = FEES["maker"]

    px = panel(args.interval, args.shuffle, args.seed, MAJORS if args.majors else None)
    etiqueta = "NULL (barajado)" if args.shuffle else "REAL"
    print(f"\n{etiqueta} · panel de {px.shape[1]} activos × {px.shape[0]} velas {args.interval}\n")
    print(f"{'lookback':>9}{'hold':>6}{'K':>4}{'neto':>10}{'Sharpe':>9}{'maxDD':>9}{'bruto':>9}{'fees':>8}")
    print("─"*66)
    mejores = []
    for lb in (24, 72, 168, 336):          # 1d, 3d, 7d, 14d en barras de 1H
        for hold in (24, 72, 168):
            for k in (3, 5, 8):
                r = backtest(px, lb, hold, k, fee)
                if not r:
                    continue
                mejores.append((r["sharpe"], lb, hold, k, r))
                if r["sharpe"] > 0.5:
                    print(f"{lb:>9}{hold:>6}{k:>4}{r['net']*100:>9.1f}%{r['sharpe']:>9.2f}"
                          f"{r['maxdd']*100:>8.1f}%{r['gross']*100:>8.1f}%{r['fees']*100:>7.1f}%")
    if mejores:
        mejores.sort(reverse=True, key=lambda x: x[0])
        sh, lb, hold, k, r = mejores[0]
        print("─"*66)
        print(f"\nMejor: lookback={lb}h hold={hold}h K={k} → Sharpe {sh:.2f}, "
              f"neto {r['net']*100:+.1f}%, {r['rebalances']} rebalanceos")
        print(f"  configs con Sharpe>0.5: {sum(1 for m in mejores if m[0] > 0.5)} de {len(mejores)}")


if __name__ == "__main__":
    main()


def walk_forward_xs(px, fee, train_bars, test_bars, grid):
    """
    Pick the config on the training window, trade only the window after it.
    Reported returns are exclusively out-of-sample — the config that produced
    each stretch was chosen without seeing it.
    """
    ret = px.pct_change()
    nets, grosses, turns, elegidas = [], [], [], []
    start = 0
    while start + train_bars + test_bars <= len(px):
        tr = px.iloc[start:start + train_bars]
        best, best_sh = None, -np.inf
        for lb, hold, k in grid:
            r = backtest(tr, lb, hold, k, fee)
            if r and r["sharpe"] > best_sh:
                best_sh, best = r["sharpe"], (lb, hold, k)
        if best is None:
            start += test_bars
            continue
        lb, hold, k = best
        elegidas.append(best)

        # rebuild weights over train+test, then keep only the test slice
        seg = px.iloc[start:start + train_bars + test_bars]
        mom = seg.pct_change(lb)
        w = pd.DataFrame(0.0, index=seg.index, columns=seg.columns)
        for i in range(lb, len(seg), hold):
            row = mom.iloc[i].dropna()
            if len(row) < 2 * k:
                continue
            ranked = row.sort_values()
            ww = pd.Series(0.0, index=seg.columns)
            ww[ranked.index[-k:]] = 1.0 / k
            ww[ranked.index[:k]]  = -1.0 / k
            w.iloc[i:i + hold] = ww.values
        w_te = w.iloc[train_bars:]
        r_te = ret.loc[w_te.index]
        g = (w_te.shift(1) * r_te).sum(axis=1).fillna(0.0)
        t = w_te.diff().abs().sum(axis=1).fillna(0.0)
        nets.append(g - t * fee); grosses.append(g); turns.append(t)
        start += test_bars

    if not nets:
        return None
    net = pd.concat(nets); gross = pd.concat(grosses); turn = pd.concat(turns)
    sd = net.std(); curve = (1 + net).cumprod()
    return dict(net=(1 + net).prod() - 1,
                sharpe=(net.mean() / sd * np.sqrt(8760)) if sd > 0 else 0.0,
                maxdd=(curve / curve.cummax() - 1).min(),
                fees=turn.sum() * fee, vol_mult=turn.sum(),
                windows=len(nets), configs=elegidas)
