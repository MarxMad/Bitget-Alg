# Bitget-Alg

Two trading strategies for Bitget USDT-M perpetuals, plus the statistical
tooling used to decide whether either was worth running.

The tooling is the point. Most of what a backtest sweep finds is noise, and the
scripts here exist to prove that before money is involved — on this universe
they killed three strategy families and left one standing.

## What is here

| | |
|---|---|
| `shared/bitget_client.py` | Bitget Unified (v3) REST client, RSA-SHA256 signing |
| `strategies/mm_bitget/` | Market maker quoting at 2.5x realised volatility |
| `strategies/cross_sectional/` | Cross-sectional momentum over 12 majors |
| `scripts/` | Data download, edge sweeps, significance tests, preflight |
| `api/`, `vercel.json` | Vercel cron + private dashboard for the momentum leg |
| `Dockerfile` | Portable container for the market maker |

## How strategies were accepted or rejected

Every candidate was scored against a **null**: the identical procedure rerun on
shuffled returns, which have no signal by construction. A result that a coin
flip matches is not an edge.

**Rejected — classic technical analysis.** Trend-following, Donchian breakouts
and z-score reversion across 33 assets produced 11 apparent winners. The same
filter on shuffled data passes **13.6 on average**. Worse than chance. Walk-forward
agreed (real 10, null range 4–12). Scanning harder makes this worse, not better:
each extra candidate is another lottery ticket.

**Accepted, weakly — cross-sectional momentum.** Long the 3 strongest of 12
majors against the 3 weakest, rebalanced daily. Walk-forward Sharpe 1.56 and
+42.9% out-of-sample against a null averaging **−0.73**, which 0 of 10 shuffled
runs reached. The null's negative mean is the informative part: on noise you pay
fees and earn nothing. p < 0.1 — evidence, not proof.

**Accepted as breakeven — market making.** Across 10 symbols, the spread capture
was +$218.05 on the training half and +$218.94 on the test half — stable to a
dollar across non-overlapping periods. Adverse selection cancels it almost
exactly, leaving net zero both halves. That is the textbook result for a market
maker without private information, and it is useful precisely as that: volume at
no cost.

## Reproducing

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env        # then fill it in

.venv/bin/python scripts/fetch_bitget_data.py --top 40 --interval 1h --days 360
.venv/bin/python scripts/scan_edges.py --interval 1H          # finds 11 "winners"
.venv/bin/python scripts/significance_check.py                # shows noise finds 13.6
.venv/bin/python scripts/walkforward.py --interval 1H
.venv/bin/python scripts/cross_sectional.py --majors
.venv/bin/python -m strategies.mm_bitget.backtest --sweep
```

## Running

Both strategies default to paper and say so in their logs.

```bash
.venv/bin/python scripts/preflight.py                          # what is blocking
docker compose up --build -d                                   # market maker
.venv/bin/python -m strategies.cross_sectional.strategy        # momentum
```

`deploy/DOCKER.md` covers 24/7 hosting; `deploy/VERCEL.md` covers the momentum
leg's cron and dashboard.

## Things worth knowing before using this

- **Fees are identical across all 787 contracts**: maker 0.020%, taker 0.060%.
  No pair is cheaper, and no VIP tier on futures pays a maker rebate — the best
  case is 0.000%.
- **Volume scales with capital, not cleverness.** The sizing table in
  `strategies/mm_bitget/README.md` gives the numbers. Below ~$30 of equity no
  order size satisfies a 3% daily risk budget, and the bot declines to trade.
- **Breakeven in expectation is not breakeven daily.** Daily sigma is $1.81 per
  symbol per $10 of order size. On a small account the variance, not the edge,
  decides the outcome.
- **A Bitget account in Unified mode cannot use the v2 API at all** — every v2
  private endpoint returns 40085 before credentials are even checked.

## Security

No credentials are in this repository, and `.gitignore` covers `.env`, `*.pem`
and `*.key`. Give the API key Trade permission but **not** Wallet: a leaked key
should be able to trade badly, never to withdraw.

## Status

Research and infrastructure are complete and tested against the live API.
Neither strategy has traded with real money. The honest next step is a forward
test on data that did not exist when the backtests ran.
