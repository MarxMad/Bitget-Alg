# Deploying to Vercel

What ships: the **cross-sectional momentum** strategy — a daily cron that ranks
12 majors by 7-day return, holds the top 3 long against the bottom 3 short, and
a private dashboard showing it work.

The market-maker leg is **not** here. It quotes continuously and reprices every
few seconds, which a cron cannot do; it needs a real server with a fixed IP.
That is phase 2.

## Files

| File | Role |
|---|---|
| `vercel.json` | cron schedule, function timeouts, `/` → dashboard |
| `api/rebalance.py` | the daily run, `CRON_SECRET`-gated |
| `api/status.py` | read-only state for the dashboard |
| `api/_store.py` | history in Upstash Redis over its REST API |
| `dashboard.html` | the dashboard |
| `.vercelignore` | keeps research, CSVs, pandas and numpy out of the bundle |

## Steps

**1. Storage**

```bash
vercel integration add upstash
```

Injects `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN`. Skip it and
everything still runs — you just lose the history, and the dashboard says so.

**2. Environment variables** — Settings → Environment Variables:

| Variable | Value |
|---|---|
| `BITGET_ACCESS_KEY` | your `bg_…` key |
| `BITGET_PASSPHRASE` | the passphrase |
| `BITGET_PRIVATE_KEY` | the **whole PEM**, `-----BEGIN` through `-----END` |
| `CRON_SECRET` | any long random string — `openssl rand -hex 32` |
| `TRADING_MODE` | `paper` (change to `live` only after forward-testing) |

`BITGET_PRIVATE_KEY` holds the key text itself, not a path — the client accepts
either. Mark all of these **Sensitive** so they cannot be read back from the UI.

Without `CRON_SECRET` the rebalance endpoint refuses every request, including
Vercel's own. That is deliberate: an unprotected public URL would let anyone
fire a rebalance at will.

**3. Make it private** — Settings → Deployment Protection → **Vercel
Authentication**, applied to Production. Only your team can open the dashboard.
Cron still works: Vercel triggers it internally, bypassing protection.

**4. Deploy**

```bash
vercel --prod
```

**5. Verify** — Deployments → Functions → Cron, hit **Run** to fire it once by
hand, then open the dashboard.

## Schedule

`10 7 * * *` — 07:10 UTC daily, matching the 24h hold the strategy was validated
at. A few minutes past the hour because Vercel's scheduler is busiest exactly on
the hour. Pro allows up to 40 crons and per-minute schedules, but do not shorten
this one: the walk-forward evidence is for a 24h hold, and a different cadence is
a different, unvalidated strategy.

## Going live

`TRADING_MODE=paper` is the default and places no orders. Leave it for ~30 days,
read the history table, and compare what it did against what the backtest
promised. Only then set `TRADING_MODE=live`.

The evidence behind this strategy is p < 0.1 and was found after searching
several strategy families. It deserves a forward test, not conviction.

## Scaling

Nothing changes in code as capital grows — position sizes come from live equity
every run.

| Capital | Per leg @ 2x | Volume/day | Profit/year (backtest) |
|---|---|---|---|
| $20 | $6.67 | ~$13 | ~$9 |
| $200 | $66.67 | ~$134 | ~$86 |
| $2,000 | $666.67 | ~$1,337 | ~$858 |

All three clear Bitget's $5 minimum per leg. Below ~$15 of equity the bot
refuses to trade rather than place a partial, unhedged book.
