#!/bin/bash
# Entrypoint for the Hermes Agent on Altare.
# Works in BOTH deploy modes:
#   - Docker: ENTRYPOINT ["/app/entrypoint.sh"], hermes at /app/venv/bin/hermes.
#   - Altare Python buildpack: start command `bash entrypoint.sh` from the
#     app root, hermes installed by `pip install -r requirements.txt` and
#     on PATH (or ~/.local/bin/hermes).
# All repo paths are derived from this script's own directory (SCRIPT_DIR);
# nothing is hardcoded to /app.
# - Sanitizes NO_PROXY (httpx mis-parses bracketed IPv6 entries; Hermes
#   only needs the loopback relay).
# - Writes ~/.hermes/.env (0600) from env vars (secrets are never in the image).
# - Seeds config.yaml, the BAW skill and the Telegram pairing approval on
#   first run only; existing state is kept on redeploy.
# - Starts the Cent AI relay (loopback only) + health server (public $PORT)
#   in the background, then execs the Telegram gateway in the foreground.
set -euo pipefail

# Repo root = directory this script lives in, resolved to absolute.
# Works when invoked as `bash entrypoint.sh` (relative, from the app root)
# and as `/app/entrypoint.sh` (Docker ENTRYPOINT).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

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

# Config: ALWAYS from the repo — the repo is the source of truth for the
# model/provider (Cent AI). This also reverts a bad model change Hermes
# made to its own live config (e.g. switching to OpenRouter, which the
# relay does not serve), since a plain restart would keep the broken file.
cp "$SCRIPT_DIR/config.yaml" "$HOME/.hermes/config.yaml"

# BAW skill: only if missing (the repo copy is the source of truth).
if [ ! -d "$HOME/.hermes/skills/binance-agentic-wallet" ]; then
  cp -r "$SCRIPT_DIR/skills/binance-agentic-wallet" "$HOME/.hermes/skills/binance-agentic-wallet"
fi

# Telegram pairing approval (seed): only if missing. This file holds no
# secret — just user 1385201625 approved — and lets the gateway recognise
# dobleh at once, since a headless container cannot run the pairing flow.
if [ ! -f "$HOME/.hermes/platforms/pairing/telegram-approved.json" ]; then
  cp "$SCRIPT_DIR/pairing/telegram-approved.json" "$HOME/.hermes/platforms/pairing/telegram-approved.json"
fi

# kart shim (best-effort, NEVER fatal): the kart CLI is self-contained
# node scripts; expose it on PATH so the BAW skill can call `kart`.
# Nothing is npm-installed here; if node is missing, skip silently.
if command -v node >/dev/null 2>&1 && [ -f "$SCRIPT_DIR/kart-cli/kart.mjs" ]; then
  KART_BIN_DIR=""
  for d in /usr/local/bin "$HOME/.local/bin"; do
    if mkdir -p "$d" 2>/dev/null && [ -w "$d" ]; then
      KART_BIN_DIR="$d"
      break
    fi
  done
  if [ -n "$KART_BIN_DIR" ]; then
    printf '#!/bin/sh\nexec node %s "$@"\n' "$SCRIPT_DIR/kart-cli/kart.mjs" > "$KART_BIN_DIR/kart" 2>/dev/null && chmod +x "$KART_BIN_DIR/kart" 2>/dev/null || true
    case ":$PATH:" in
      *":$KART_BIN_DIR:"*) ;;
      *) export PATH="$KART_BIN_DIR:$PATH" ;;
    esac
    echo "[entrypoint] kart shim installed at $KART_BIN_DIR/kart"
  else
    echo "[entrypoint] kart shim skipped: no writable bin dir"
  fi
else
  echo "[entrypoint] node not found, kart shim skipped"
fi

# Cent AI relay (background, loopback only — the paid key never leaves
# the container) and health server (background, public $PORT).
python3 "$SCRIPT_DIR/relay-altare.py" >> "$HOME/relay.log" 2>&1 &
python3 "$SCRIPT_DIR/health.py" >> "$HOME/health.log" 2>&1 &

# Wait until the relay is listening (max ~15s); fail loudly otherwise so
# Altare shows the crash instead of a silent dead gateway.
for _ in $(seq 1 30); do
  if python3 -c "import socket; s=socket.create_connection(('127.0.0.1',8787),timeout=1); s.close()" 2>/dev/null; then
    break
  fi
  sleep 0.5
done

# Resolve the hermes CLI: PATH first (buildpack `pip install`), then the
# Docker venv, then a pip --user install. Fail loudly if none exists.
if command -v hermes >/dev/null 2>&1; then
  HERMES="$(command -v hermes)"
elif [ -x /app/venv/bin/hermes ]; then
  HERMES="/app/venv/bin/hermes"
elif [ -x "$HOME/.local/bin/hermes" ]; then
  HERMES="$HOME/.local/bin/hermes"
else
  echo "[entrypoint] FATAL: hermes CLI not found (not on PATH, no /app/venv/bin/hermes, no ~/.local/bin/hermes). Install command must be: pip install -r requirements.txt" >&2
  exit 1
fi

# Telegram gateway in the foreground (same as `hermes.sh gateway run`).
exec "$HERMES" gateway run
