#!/usr/bin/env python3
"""
How many assets would pass the scan_edges filter on data with NO signal?

Shuffles each asset's returns (destroying time structure, preserving the return
distribution and fat tails), rebuilds a price series, and runs the identical
best-of-grid train/test selection. If the shuffled pass count is close to the
real one, the real result is noise dressed as edge.
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.scan_edges import load, evaluate, FAMILIES, BUILDERS, FEES

FEE  = FEES["maker"]
BPY  = 8760
RUNS = 5


def best_of_grid(df):
    """Same selection rule as scan_edges: rank on train, report test."""
    cut = int(len(df) * 0.66)
    tr, te = df.iloc[:cut], df.iloc[cut:]
    mejor = None
    for fam, grid in FAMILIES.items():
        build = BUILDERS[fam]
        for params in grid:
            r_tr = evaluate(tr.close, build(tr, **params), FEE, BPY)
            if not r_tr or r_tr["trades"] < 20:
                continue
            if mejor is None or r_tr["sharpe"] > mejor[0]["sharpe"]:
                r_te = evaluate(te.close, build(te, **params), FEE, BPY)
                if r_te:
                    mejor = (r_tr, r_te)
    if not mejor:
        return False
    r_tr, r_te = mejor
    return r_tr["net"] > 0 and r_te["net"] > 0 and r_te["edge_bps"] > 0


def shuffled(df, rng):
    ret = df.close.pct_change().dropna().to_numpy(copy=True)
    rng.shuffle(ret)
    price = df.close.iloc[0] * np.cumprod(1 + ret)
    out = pd.DataFrame(index=df.index[1:])
    out["close"] = price
    out["open"]  = price
    # highs/lows from the same bar's range scale, so breakout logic stays meaningful
    rel_h = (df.high / df.close).to_numpy(copy=True)[1:]
    rel_l = (df.low / df.close).to_numpy(copy=True)[1:]
    rng.shuffle(rel_h); rng.shuffle(rel_l)
    out["high"] = price * rel_h
    out["low"]  = price * rel_l
    out["volume"] = df.volume.values[1:]
    return out


def main():
    files = sorted(glob.glob("data/bitget/*_1H.csv"))
    rng = np.random.default_rng(42)
    print(f"{len(files)} activos · {RUNS} repeticiones sobre datos barajados\n")
    totals = []
    for run in range(RUNS):
        passed = 0
        for path in files:
            df = load(path)
            if len(df) < 400:
                continue
            if best_of_grid(shuffled(df, rng)):
                passed += 1
        totals.append(passed)
        print(f"  repetición {run+1}: {passed} de {len(files)} 'pasaron' sobre ruido puro")
    m = np.mean(totals)
    print(f"\n  Promedio esperado por azar: {m:.1f} activos")
    print(f"  Resultado real del escaneo: 11 activos")
    if m >= 11 * 0.7:
        print("\n  ⚠️  El resultado real NO se distingue del azar.")
    else:
        print(f"\n  El resultado real supera al azar por {11/max(m,0.1):.1f}x — hay algo, "
              f"pero {m:.0f} de los 11 siguen siendo falsos positivos esperados.")


if __name__ == "__main__":
    main()
