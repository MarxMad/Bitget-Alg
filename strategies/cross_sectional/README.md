# Cross-Sectional Momentum (Bitget)

Ranks 12 established majors by their trailing 7-day return, goes long the 3
strongest and short the 3 weakest in equal size, and rebalances daily. It never
forecasts one asset's direction — the bet is that *relative* strength persists
for a few days. Long and short in equal dollars cancels most market exposure,
leaving only the dispersion between assets.

## Why this one, and not the others

A sweep of trend-following, breakouts and mean-reversion across 33 Bitget assets
produced 11 apparent winners. Rerunning the identical filter on **shuffled
returns** — data with no signal by construction — passed 13.6 on average. The
real result was worse than chance. Walk-forward said the same (real 10, null
range 4–12). None of that is deployable, and scanning harder makes it worse:
every extra candidate is another lottery ticket.

This strategy is the only thing that separated from its null.

| | Walk-forward (real) | Null, 10 shuffled runs |
|---|---|---|
| Out-of-sample return | **+42.9%** | mean −27% |
| Sharpe | **1.56** | mean **−0.73**, max 1.27 |
| Max drawdown | −24.1% | — |
| Runs reaching the real Sharpe | — | **0 of 10** |

The null's *negative* mean is the part that matters: on noise you pay fees and
earn nothing, so you lose. Real data earns. Configs were chosen on each training
window without seeing the window they were traded on — 9 windows, 90d train /
30d test.

## What this evidence is not

**p < 0.1, not p < 0.01.** Ten null runs is a small sample. Real evidence, not proof.

**One regime.** 360 days of one market. Cross-sectional momentum suffers when
leadership rotates abruptly.

**Found after searching.** Several strategy families were tested before this one
worked. Reporting the winner of a search inflates confidence — discount accordingly.

So it ships in **paper mode by default**. Forward-test ~30 days on data that did
not exist when the backtest ran, then decide.

## Running

```bash
.venv/bin/python -m strategies.cross_sectional.strategy            # paper (default)
.venv/bin/python -m strategies.cross_sectional.strategy --once     # one cycle, then exit
.venv/bin/python -m strategies.cross_sectional.strategy --live     # real orders
```

Needs `BITGET_ACCESS_KEY`, `BITGET_PASSPHRASE`, `BITGET_PRIVATE_KEY_PATH` in `.env`.

## Sizing

K=3 means six simultaneous legs. Each must clear Bitget's $5 minimum or the book
ends up lopsided — some legs filled, others rejected, leaving unhedged
directional risk. At 2x leverage that needs **$15 of equity minimum**; the bot
refuses to trade below it rather than placing a partial book.

## Volume

~244x equity per year. Pairing it with a market maker — whose measured cost is
0.032% of the volume it generates — lets the momentum profit fund the MM's drag:
about 1,341x equity of extra volume at net zero. Combined ≈ **1,585x equity per
year** at breakeven, and the mix is a dial between profit and volume.

Reproduce: `scripts/cross_sectional.py`, `scripts/walkforward.py`,
`scripts/simulate_mm.py`.
