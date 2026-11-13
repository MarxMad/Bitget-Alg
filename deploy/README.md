# Running the bot 24/7 without your laptop

Your laptop sleeping mid-position is a real risk: nothing closes a losing trade
while the machine is asleep. A server also gives you a **fixed IP**, which lets
you bind the Bitget API key to it — a key with no IP binding can be degraded to
read-only or expired after 90 days.

## Free option: Oracle Cloud Always Free

Genuinely free with no time limit — 4 ARM cores and 24 GB RAM, far more than
this bot needs. Requires a card for identity verification; it is not charged
while you stay on Always Free shapes.

1. Sign up at cloud.oracle.com, pick your home region carefully (it cannot be changed)
2. Create a VM instance: shape **VM.Standard.A1.Flex**, Ubuntu 22.04, 1 OCPU / 6 GB
3. Save the SSH private key it gives you
4. Networking → add an ingress rule only if you want the dashboard reachable

ARM capacity in popular regions is often exhausted; retry over a few days or
pick a quieter region.

## Paid option: $4–6/month

Hetzner CX22 (~€4), Contabo, or DigitalOcean ($6). Simpler, always available,
and the cost is meaningful only against a tiny account — at $20 of capital a
$5/month server is 25% of the account per month, so prefer the free tier until
the account justifies it.

## Setup, once you have a server

```bash
ssh ubuntu@<your-ip>

sudo adduser --disabled-password --gecos "" bot
sudo -u bot -i

git clone https://github.com/MarxMad/Bitget-Alg.git Bitget-Algoritmo-API
cd Bitget-Algoritmo-API
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
mkdir -p logs
```

Copy your credentials over from your Mac — never paste the private key into a
chat or commit it:

```bash
scp ~/.bitget/bitget_private_key.pem ubuntu@<your-ip>:/tmp/
scp .env ubuntu@<your-ip>:/tmp/

# on the server
sudo mv /tmp/bitget_private_key.pem /home/bot/.bitget/
sudo mv /tmp/.env /home/bot/Bitget-Algoritmo-API/.env
sudo chown -R bot:bot /home/bot/.bitget /home/bot/Bitget-Algoritmo-API/.env
sudo chmod 600 /home/bot/.bitget/bitget_private_key.pem /home/bot/Bitget-Algoritmo-API/.env
```

Edit `.env` so `BITGET_PRIVATE_KEY_PATH=/home/bot/.bitget/bitget_private_key.pem`.

Then install the service:

```bash
sudo cp /home/bot/Bitget-Algoritmo-API/deploy/cross-sectional.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cross-sectional
```

## Day to day

```bash
systemctl status cross-sectional          # is it alive
journalctl -u cross-sectional -f          # follow it live
tail -f ~/Bitget-Algoritmo-API/logs/cross_sectional.log
sudo systemctl stop cross-sectional       # stop it
```

The service restarts on crash but gives up after 5 failures in 10 minutes,
so a bot that cannot start stays down loudly instead of hammering the exchange.

## Before you switch off paper mode

1. Bind the server's IP in Bitget (Edit on the API key — permissions and IP are
   editable; the public key is not)
2. Leave it in paper mode ~30 days and read the log
3. Only then add `--live` to `ExecStart`

The service file ships **without** `--live` on purpose.

---

# Option: no server at all — GitHub Actions

The strategy rebalances once every 24h, so it does not need a machine that stays
on. It needs a job that runs for about a minute a day, and GitHub already runs
those for free — unlimited minutes on a public repo, 2,000/month on a private
one (this uses roughly 30).

`.github/workflows/rebalance.yml` does it. Setup:

1. Repo → **Settings → Secrets and variables → Actions → New repository secret**

   | Secret | Value |
   |---|---|
   | `BITGET_ACCESS_KEY` | your `bg_…` key |
   | `BITGET_PASSPHRASE` | the passphrase you set |
   | `BITGET_PRIVATE_KEY` | the whole PEM, `-----BEGIN` through `-----END`, newlines included |

2. Actions tab → **Run workflow** to trigger it by hand and confirm it works
3. After that it runs itself daily at 07:10 UTC

## What this costs you

**No IP binding.** GitHub's runners get a different IP every run, so you cannot
whitelist one in Bitget. That is the real tradeoff against a VPS.

**Public logs on a public repo.** The workflow sets `REDACT_BALANCES=1`, which
keeps equity and order sizes out of the log. Signals still print — anyone can
compute those from public prices, so hiding them buys nothing. If you would
rather not publish even that, make the repo private; 2,000 free minutes is far
more than this needs.

**Scheduled workflows pause after 60 days with no repo activity.** A commit or a
manual run resets the clock.

**The schedule drifts.** GitHub queues cron jobs and can run them minutes late
under load. Irrelevant for a daily rebalance; fatal for a market maker.

**Your key lives in GitHub Secrets.** Encrypted, and not exposed to forks or
pull requests. The blast radius is bounded by the key's own permissions: yours
has Trade and Manage but no Wallet, so a leak means bad trades, never withdrawals.

## When you outgrow it

The market-maker half of the merged system quotes continuously and reprices
every few seconds. That genuinely needs a server, and it needs the fixed IP.
Use Actions for the momentum leg now; move both to a VPS when you add the MM.

# Option: hardware you already own

A Raspberry Pi, an old laptop, or an Android phone running Termux all work, cost
nothing monthly, and give you a stable home IP to whitelist. The catch is your
home internet and power: if either drops while a position is open, nothing
closes it. Fine for the daily momentum leg, risky for a market maker.

# Option: a cheap VPS that is not AWS or Oracle

| Provider | Price | Notes |
|---|---|---|
| **Hetzner** CX22 | ~€3.79/mo | Cheapest reliable option; EU/US locations |
| **Contabo** VPS S | ~€5/mo | More RAM per euro, slower support |
| **DigitalOcean** | $4–6/mo | Simplest UI, good docs |
| **Vultr** | $5/mo | Many regions |
| **Google Cloud** | free e2-micro | Always-free tier in us-west1/central1/east1; still needs a card |

Any of them gives a fixed IP and runs the systemd unit above.
