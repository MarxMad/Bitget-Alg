# Deploying the market maker with Docker

## Check what is blocking first

```bash
.venv/bin/python strategies/mm_bitget/preflight.py
```

It asks the live account, rather than assuming. The trading-permission check
actually places an order — priced far from the market and post_only, so it
cannot fill — because that is the only way to know one would be accepted.

Fix anything it flags (missing credentials, KYC, zero balance) before going live.
Paper mode runs without any of that.

## Run it locally, in paper, right now

```bash
docker compose up --build -d
docker compose logs -f market-maker
curl -s localhost:8080/status | python3 -m json.tool
docker compose down
```

Your laptop has to stay awake for this, so it is for watching the mechanics —
quote widths, inventory, cancellations — not for a forward test. A laptop that
sleeps with inventory open has nothing closing it.

## Run it on a server, 24/7

Any host with Docker. Hetzner CX22 (~€3.79/mo) gives the fixed IP you can then
bind in Bitget.

```bash
ssh root@<server-ip>

curl -fsSL https://get.docker.com | sh
adduser --disabled-password --gecos "" bot
usermod -aG docker bot
su - bot

git clone https://github.com/MarxMad/Bitget-Alg.git Bitget-Algoritmo-API
cd Bitget-Algoritmo-API
```

Copy credentials from your Mac — never commit them, never paste a private key
into a chat:

```bash
# from your Mac
scp .env bot@<server-ip>:~/Bitget-Algoritmo-API/.env
scp ~/.bitget/bitget_private_key.pem bot@<server-ip>:~/.bitget/
```

On the server, point `.env` at the copied key and lock both down:

```bash
sed -i 's|^BITGET_PRIVATE_KEY_PATH=.*|BITGET_PRIVATE_KEY_PATH=/home/bot/.bitget/bitget_private_key.pem|' .env
chmod 600 .env ~/.bitget/bitget_private_key.pem
```

`docker-compose.yml` mounts `.env`; add the key path to `volumes` so the
container can read it:

```yaml
    volumes:
      - ./logs:/app/logs
      - /home/bot/.bitget:/home/bot/.bitget:ro
```

Then:

```bash
docker compose up --build -d
docker compose logs -f
```

It restarts on crash and on reboot (`restart: unless-stopped`).

## Bind the IP

Once the server is up, Bitget → API keys → Edit on "Zacatlan" → add the server's
IP. Permissions and IP are editable; the public key is not.

## Going live

`docker-compose.yml` ships with `MM_ARGS: ""` — paper. Going live is one edit:

```yaml
      MM_ARGS: "--live"
```

then `docker compose up -d`. Do it only after preflight is clean and the bot has
run ~30 days in paper against data that did not exist when it was backtested.

The strategy is breakeven in expectation, not profitable. At small equity the
variance decides the outcome, not the edge — see the sizing table in
`strategies/mm_bitget/README.md`.

## Watching it

```bash
docker compose logs -f --tail 50
curl -s localhost:8080/status | python3 -m json.tool
curl -s localhost:8080/health          # 503 when the last cycle is over 5 min old
docker compose restart market-maker
docker compose down                     # stop; open orders are NOT cancelled
```

`docker compose down` stops the process but leaves resting orders on the
exchange. Cancel them from the Bitget UI, or let the bot restart and replace
them.
