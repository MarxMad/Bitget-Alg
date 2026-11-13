# Market Maker (Bitget)

Quotes both sides continuously at **2.5x the asset's rolling 1m volatility**,
requoting every 15s only when price has actually drifted.

## Why 2.5x, and why the old bot lost

The first version quoted a fixed mid±0.02% (replay it with `replay_fixed_spread.py`). BTC's book is 0.0001% wide,
so those orders rest far outside the touch and only fill when price runs through
them — buying dips, selling rips. That is mean reversion with negative
expectancy, not spread capture, and it lost 0.025–0.049% of every dollar of
volume it generated.

Width has to scale with how much the asset actually moves. Measured over 56
asset-days of Bitget 1m data (SOL, ETH, BTC, XLM), `strategies/mm_bitget/optimize.py`:

| Width | P&L/day | Days up | Volume/day | |
|---|---|---|---|---|
| 2.0x | −$0.31 | 34% | $2,713 | loses to adverse selection |
| **2.5x** | **+$0.02** | **52%** | **$1,652** | **breakeven, max volume** ← default |
| 3.0x | +$0.28 | 62% | $1,034 | profitable, less volume |
| 4.0x | +$0.23 | 62% | $444 | profitable, little volume |

Per $10 of order size. 2.5x is the widest-volume point whose P&L is
statistically zero: +$0.02 against a $0.17 standard error. That is exactly the
brief — maximum volume without paying for it.

Choose 3.0x instead if you would rather earn than turn over.

## Why this is not wash trading

Wash trading means trading with yourself to fake volume. Four properties make
that mechanically impossible, each enforced in code:

1. **post_only on every order.** The exchange rejects any quote that would
   cross, so this bot is never the aggressor — and an order that never takes
   liquidity cannot hit your own resting order.
2. **The quote pair cannot cross.** `quote_prices` returns None rather than a
   bid above its own ask.
3. **Requote throttling.** Quotes move only on real drift. Cancel/replace storms
   against a still book are the layering pattern surveillance looks for.
4. **Real risk on every fill.** Counterparties are other traders, the inventory
   is genuine, and P&L can go against you — which is what makes the volume real.

## Risk, honestly

Breakeven on average is not breakeven every day. Daily P&L standard deviation is
$1.30 per $10 of order size; the worst day observed was −$3.44.

| Equity | Order | Volume/day (2 syms) | Worst observed day |
|---|---|---|---|
| $20 | $5 | $1,652 | **17.2% of the account** |
| $200 | $20 | $6,606 | 6.9% |
| $2,000 | $100 | $33,032 | 3.4% |

At $20 this has a roughly 30% monthly standard deviation around zero expected
return. That is a coin flip that can halve the account. **$200 is the sane
floor; $2,000 makes the variance a rounding error.**

Guards: `daily_loss_limit` 10% halts and cancels; `max_inventory_orders` stops
the side that would grow a capped position; `max_gross_leverage` 5x caps total
notional.

## Blocker

Bitget returns `40035 — complete KYC first` on every order attempt. Nothing
trades, live or not, until identity verification is done on the account.

## Sizing: the bot reads equity and resizes itself

`order_usdt` is not configured — `size_from_equity` recomputes it every cycle
from live account equity, so the book grows with the account without a redeploy.

Two limits bind it. Daily sigma must stay inside `risk_budget` (3% of equity by
default), and peak inventory must stay inside `max_gross_leverage` (5x). Measured
constants, from 15 days of Bitget 1m data across 7 symbols at the 2.5x width:

| | per symbol, per $10 of order |
|---|---|
| Volume | $1,949/day (linear in both) |
| Daily sigma | $1.81, scaling as **n^0.82** |
| Peak inventory | 11x order size |

That exponent drives the design. Volume grows linearly with symbol count while
risk grows as n^0.82, so spreading across symbols is strictly better than growing
an order: same volume, less risk. The sizer fills all 10 symbols at the $5
minimum before it grows a single order.

### Thresholds at the default 3% risk budget

| Equity | Order | Symbols | Volume/day | Volume/month | sigma/day |
|---|---|---|---|---|---|
| $20 | — | — | — | — | **declines to trade** |
| $35 | $5.80 | 1 | $1,130 | $33,913 | $1.05 |
| $100 | $5.32 | 4 | $4,147 | $124,424 | $3.00 |
| $200 | $5.02 | 10 | $9,784 | $293,519 | $6.00 |
| $500 | $12.54 | 10 | $24,440 | $733,214 | $15.00 |
| $2,000 | $50.17 | 10 | $97,781 | $2,933,440 | $60.00 |
| $5,000 | $125.43 | 10 | $244,463 | $7,333,892 | $150.00 |
| $20,000 | $501.73 | 10 | $977,872 | $29,336,153 | $600.00 |

At $20 the largest order the 3% budget allows is $3.31, under the exchange's $5
minimum, so the bot refuses rather than quietly taking more risk than asked.

### Starting at $20 anyway

Raise `risk_budget` to 0.05 and it trades: one symbol, $5.52 orders, ~$1,076/day
of volume, sigma $1.00/day. Understand what that buys: a sustained −2 sigma
streak halves a $20 account in **5 days**. The strategy is breakeven in
expectation; at this size the variance, not the edge, decides the outcome.

$100 is where it starts behaving — 8 symbols, sigma back inside 3%.

## Running

```bash
python -m strategies.mm_bitget.strategy                    # paper
python -m strategies.mm_bitget.strategy --once             # one cycle
python -m strategies.mm_bitget.strategy --live --order-usdt 5
```

Needs an always-on host — it requotes every 15s, which no cron can do. See
`deploy/VERCEL.md` for why the momentum leg fits Vercel and this one does not.
