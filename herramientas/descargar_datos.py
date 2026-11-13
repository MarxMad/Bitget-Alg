#!/usr/bin/env python3
"""
Download Bitget USDT-M perpetual candles into CSVs for research.

    .venv/bin/python herramientas/descargar_datos.py --top 30 --interval 1h --days 360
    .venv/bin/python herramientas/descargar_datos.py --symbols XLMUSDT,SOLUSDT --interval 15m --days 180

Writes data/bitget/<SYMBOL>_<interval>.csv with columns ts,open,high,low,close,volume,turnover.
Public endpoints only — no credentials needed.
"""
import argparse
import csv
import os
import sys
import time
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.bitget_client import BitgetClient, unwrap

OUT_DIR   = "data/bitget"
# Deep history comes from the v2 PUBLIC history-candles endpoint. v3's
# /market/candles only serves the most recent 1000 bars (no paging past them)
# and v3's history-candles caps at 100/call, so v2's 200/call is the fastest
# public route. Unified-account mode blocks v2 PRIVATE endpoints only.
HIST_PATH = "/api/v2/mix/market/history-candles"
MAX_LIMIT = 200           # v2 rejects >200 with code 40053
# Bitget's interval strings are case-sensitive: minutes lowercase, hours/days
# uppercase. "1h" is rejected with 40020 while "1H" works.
INTERVAL_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
               "1H": 3_600_000, "4H": 14_400_000, "6H": 21_600_000,
               "12H": 43_200_000, "1D": 86_400_000}


def normalize_interval(iv: str) -> str:
    """Accept 1h/4h/1d spellings and map them to Bitget's casing."""
    iv = iv.strip()
    if iv in INTERVAL_MS:
        return iv
    upper = iv[:-1] + iv[-1].upper()
    return upper if upper in INTERVAL_MS else iv


def retry(fn, tries=4):
    """The connection to api.bitget.com drops often enough to need this."""
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))


def liquid_universe(client, top_n):
    """Top N USDT perps by 24h turnover."""
    rows = []
    for d in unwrap(retry(lambda: client.get_tickers())):
        try:
            rows.append((d["symbol"], float(d.get("turnover24h") or 0)))
        except (TypeError, ValueError, KeyError):
            continue
    rows.sort(key=lambda x: -x[1])
    return [s for s, _ in rows[:top_n]]


def fetch_symbol(client, symbol, interval, days):
    step = INTERVAL_MS[interval]
    need = int(days * 86_400_000 / step)
    end  = int(time.time() * 1000)
    rows = []
    while len(rows) < need:
        params = {"symbol": symbol, "productType": "USDT-FUTURES",
                  "granularity": interval, "limit": str(MAX_LIMIT),
                  "endTime": str(end)}
        resp = retry(lambda: client._get(HIST_PATH, params, signed=False))
        batch = resp.get("data") or []
        if not batch:
            break
        rows = batch + rows
        oldest = int(batch[0][0])
        if oldest >= end:
            break          # no older data available; stop rather than spin
        end = oldest
        time.sleep(0.15)   # stay well under the rate limit
    # dedupe by timestamp and keep chronological order
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: int(r[0])):
        if r[0] not in seen:
            seen.add(r[0])
            out.append(r)
    return out[-need:] if need else out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", help="comma-separated, e.g. XLMUSDT,SOLUSDT")
    ap.add_argument("--top", type=int, default=0, help="top N by 24h turnover")
    ap.add_argument("--interval", default="1h")
    ap.add_argument("--days", type=int, default=360)
    args = ap.parse_args()

    args.interval = normalize_interval(args.interval)
    if args.interval not in INTERVAL_MS:
        sys.exit(f"interval inválido. Válidos: {', '.join(INTERVAL_MS)}")

    client = BitgetClient()
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    elif args.top:
        symbols = liquid_universe(client, args.top)
    else:
        sys.exit("pass --symbols or --top")

    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"{len(symbols)} símbolos · {args.interval} · {args.days} días\n")

    for i, sym in enumerate(symbols, 1):
        try:
            rows = fetch_symbol(client, sym, args.interval, args.days)
        except Exception as e:
            print(f"  [{i}/{len(symbols)}] {sym:<14} ❌ {type(e).__name__}")
            continue
        if not rows:
            print(f"  [{i}/{len(symbols)}] {sym:<14} ❌ sin datos")
            continue
        path = os.path.join(OUT_DIR, f"{sym}_{args.interval}.csv")
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["ts", "open", "high", "low", "close", "volume", "turnover"])
            w.writerows(rows)
        d0 = dt.datetime.fromtimestamp(int(rows[0][0]) / 1000).date()
        d1 = dt.datetime.fromtimestamp(int(rows[-1][0]) / 1000).date()
        print(f"  [{i}/{len(symbols)}] {sym:<14} {len(rows):>6} velas  {d0} → {d1}")

    print(f"\n✅ en {OUT_DIR}/")


if __name__ == "__main__":
    main()
