# Hermes Agent (Nous Research) on Altare — see README.md
# No secrets are baked into this image. All secrets arrive as env vars
# at runtime (TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USERS, CENTAI_API_KEY).
FROM --platform=linux/amd64 python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/hermes

RUN mkdir -p /home/hermes /app && \
    apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates gnupg && \
    curl -fsSL https://deb.nodesource.com/setup_24.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Hermes Agent v0.19.0 via pip (the official uv-based installer times
# out downloading wheels through proxied egress; pip works).
RUN python3 -m venv /app/venv && \
    /app/venv/bin/pip install --no-cache-dir hermes-agent==0.19.0

# Binance Agentic Wallet CLI (global install provides /usr/local/bin/baw).
RUN npm install -g @binance/agentic-wallet@1.12.0 && \
    test -x /usr/local/bin/baw

# kart CLI (Agent Cards) — self-contained node scripts, no npm deps
# (Node 20+). Verified with `kart help` below.
COPY kart-cli/ /app/kart-cli/
RUN printf '#!/bin/sh\nexec node /app/kart-cli/kart.mjs "$@"\n' > /usr/local/bin/kart && \
    chmod +x /usr/local/bin/kart && \
    timeout 30 kart help > /dev/null && echo "kart OK"

COPY relay-altare.py health.py entrypoint.sh config.yaml /app/
COPY pairing/ /app/pairing/
COPY skills/ /app/skills/
RUN chmod +x /app/entrypoint.sh && \
    python3 -m py_compile /app/relay-altare.py /app/health.py && \
    bash -n /app/entrypoint.sh

WORKDIR /app
EXPOSE 8080
ENTRYPOINT ["/app/entrypoint.sh"]
