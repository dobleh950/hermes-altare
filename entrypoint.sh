#!/bin/bash
# Entrypoint for the Hermes Agent container on Altare.
# - Sanitizes NO_PROXY (httpx mis-parses bracketed IPv6 entries; Hermes
#   only needs the loopback relay).
# - Writes ~/.hermes/.env (0600) from env vars (secrets are never in the image).
# - Seeds config.yaml, the BAW skill and the Telegram pairing approval on
#   first run only; existing state is kept on redeploy.
# - Starts the Cent AI relay (loopback only) + health server (public $PORT)
#   in the background, then execs the Telegram gateway in the foreground.
set -euo pipefail

export NO_PROXY=localhost,127.0.0.1
export no_proxy=localhost,127.0.0.1

# Persistent state: Altare keeps files in the app's data folder across
# redeploys; files elsewhere are replaced. If DATA_DIR is set to that
# folder, use it as HOME so ~/.hermes (pairing, sessions, state) and
# ~/.agent-cards (kart session) survive redeploys.
if [ -n "${DATA_DIR:-}" ]; then
  export HOME="$DATA_DIR"
else
  export HOME="${HOME:-/home/hermes}"
fi
mkdir -p "$HOME/.hermes" "$HOME/.hermes/skills" "$HOME/.hermes/platforms/pairing"

: "${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN env var is required}"
: "${CENTAI_API_KEY:?CENTAI_API_KEY env var is required}"
TELEGRAM_ALLOWED_USERS="${TELEGRAM_ALLOWED_USERS:-1385201625}"

# Gateway reads the token from ~/.hermes/.env (0600), as on the VM.
printf 'TELEGRAM_BOT_TOKEN=%s\nTELEGRAM_ALLOWED_USERS=%s\n' \
  "$TELEGRAM_BOT_TOKEN" "$TELEGRAM_ALLOWED_USERS" > "$HOME/.hermes/.env"
chmod 600 "$HOME/.hermes/.env"

# Config: only on first run, so redeploys keep existing state.
if [ ! -f "$HOME/.hermes/config.yaml" ]; then
  cp /app/config.yaml "$HOME/.hermes/config.yaml"
fi

# BAW skill: only if missing (the image copy is the source of truth).
if [ ! -d "$HOME/.hermes/skills/binance-agentic-wallet" ]; then
  cp -r /app/skills/binance-agentic-wallet "$HOME/.hermes/skills/binance-agentic-wallet"
fi

# Telegram pairing approval (seed): only if missing. This file holds no
# secret — just user 1385201625 approved — and lets the gateway recognise
# dobleh at once, since a headless container cannot run the pairing flow.
if [ ! -f "$HOME/.hermes/platforms/pairing/telegram-approved.json" ]; then
  cp /app/pairing/telegram-approved.json "$HOME/.hermes/platforms/pairing/telegram-approved.json"
fi

# Cent AI relay (background, loopback only — the paid key never leaves
# the container) and health server (background, public $PORT).
python3 /app/relay-altare.py >> "$HOME/relay.log" 2>&1 &
python3 /app/health.py >> "$HOME/health.log" 2>&1 &

# Wait until the relay is listening (max ~15s); fail loudly otherwise so
# Altare shows the crash instead of a silent dead gateway.
for _ in $(seq 1 30); do
  if python3 -c "import socket; s=socket.create_connection(('127.0.0.1',8787),timeout=1); s.close()" 2>/dev/null; then
    break
  fi
  sleep 0.5
done

# Telegram gateway in the foreground (same as `hermes.sh gateway run`).
exec /app/venv/bin/hermes gateway run
