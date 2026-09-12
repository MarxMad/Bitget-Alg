# Runs the market maker as a long-lived process. Deliberately portable: the same
# image runs on a plain VPS via docker compose, on Railway, on Fly, or on any
# container host — so the choice of provider stays reversible.
FROM python:3.12-slim

# curl for the healthcheck; nothing else is needed at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Only the live path's dependencies. pandas/numpy are research-only and would
# roughly triple the image for code that never runs here.
COPY requirements-vercel.txt .
RUN pip install --no-cache-dir -r requirements-vercel.txt python-dotenv

COPY shared/ ./shared/
COPY strategies/mm_bitget/ ./strategies/mm_bitget/
COPY strategies/__init__.py ./strategies/

# Never run as root: a container that only speaks HTTPS to one API has no need
# for it, and it limits what a dependency compromise can reach.
RUN useradd -m -u 10001 bot && chown -R bot:bot /app
USER bot

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 STATUS_PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS http://localhost:8080/health || exit 1

# Paper by default. Going live is an explicit change to this command.
CMD ["python", "-m", "strategies.mm_bitget.strategy"]
