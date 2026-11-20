# Hermes Agent on Altare

Hermes Agent v0.19.0 (Nous Research) packaged for deployment on
[Altare](https://console.altare.gg) (PaaS: pick a GitHub repo, it
rebuilds on push). Chat with it on Telegram; brain is Cent AI
`hy4-flash:free` ($0.00/token). It ships with **only** the
`binance-agentic-wallet` skill (dobleh's order: "khusus binance
wallet skill aja").

This repo mirrors the working install on the VM
(`~/workspace/hermes-install/` + `~/.hermes/`), adapted for a
container with no Secure Vault and no interactive shell.

## How it runs

- **Relay** (`relay-altare.py`) listens on `127.0.0.1:8787` only and
  forwards Hermes's OpenAI-compatible requests (`/v1/*`, SSE
  supported) to `https://api.cent-ai.dev/v1`, attaching the Cent AI
  key from the `CENTAI_API_KEY` env var. The relay is loopback-only,
  so the key never leaves the container.
- **Gateway** (`hermes gateway run`, foreground) polls Telegram.
  Token comes from the `TELEGRAM_BOT_TOKEN` env var, written to
  `~/.hermes/.env` (0600) at container start.
- **Health server** (`health.py`) listens on `$PORT` (default 8080)
  and answers `200 {"status":"ok"}` on `/health`, `404` otherwise.
  It does NOT proxy to the relay.
- **State** lives under `$HOME/.hermes` (config, pairing, sessions).
  Set `DATA_DIR` to Altare's persistent data folder so state survives
  redeploys (files outside the data folder are replaced on redeploy).
  Without `DATA_DIR`, state is ephemeral and the pairing seed is
  re-applied on each start.
- **Pairing seed** (`pairing/telegram-approved.json`) holds no secret —
  just Telegram user `1385201625` approved — so the gateway
  recognises dobleh at once. A headless container cannot run the
  pairing flow, hence the seed.

## Secrets — none in this image

No API key, bot token, or wallet session is baked into the image.
Secrets arrive as Altare app env vars at runtime:

| Env var | Value |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token (from @BotFather) |
| `TELEGRAM_ALLOWED_USERS` | `1385201625` (dobleh only) |
| `CENTAI_API_KEY` | Cent AI API key |
| `DATA_DIR` | (optional) Altare persistent data folder path |
| `PORT` | (optional, default `8080`) Altare sets this |

## Deploy on Altare

1. Push this repo to GitHub (account `dobleh950` is already
   connected to Altare).
2. Altare console → **Create app** → **GitHub** tab → pick this repo.
   Altare rebuilds on every push.
3. Set the env vars above in the app's environment settings
   (mark the token/key as secret).
4. Deploy. Check the app logs: you should see `[relay] listening`,
   `[health] listening`, then the gateway connecting to Telegram.
5. Verify: send the bot a Telegram message (e.g. `cek wallet`).
   It should reply from `hy4-flash:free` via Cent AI.

## Verify locally (no Docker needed for these checks)

```bash
python3 -m py_compile relay-altare.py health.py
bash -n entrypoint.sh
node kart-cli/kart.mjs help        # kart 0.26.0, no login needed
```

## KNOWN LIMITS — read before relying on this

- **BAW (Binance Agentic Wallet) login cannot run headless.**
  `baw auth signin` needs an interactive QR scan in the Binance App.
  The container has no interactive shell, so `baw` starts **not
  logged in** and every wallet command (`baw wallet status`,
  `kart ...`, free mints) will fail until a login path exists —
  e.g. an Altare console/exec into the running container, or a
  BAW session seeded into the data folder. The chat side of Hermes
  works without BAW; the wallet skill does not. Do not pretend
  otherwise.
- **Outbound network is assumed.** The relay must reach
  `api.cent-ai.dev` and the gateway `api.telegram.org` from the
  container. If Altare blocks outbound traffic, nothing works.
- **Sleep policy unknown.** If Altare sleeps idle apps, the Telegram
  gateway stops polling while asleep. Confirm in the Altare
  dashboard whether the app runs 24/7 on the current plan/credits.
- **Data folder path unverified.** `DATA_DIR` must be set to the
  exact path Altare exposes as the persistent data folder; the
  correct value is whatever the Altare app settings show.
- **Model lanes:** only Cent AI `hy4-flash:free` is wired. FreeModel
  is exhausted (402), Groq and Opus are vetoed by dobleh — do not
  wire them in.

## Files

| File | What it is |
| --- | --- |
| `Dockerfile` | `python:3.12-slim` + Node 24 + `hermes-agent==0.19.0` + BAW 1.12.0 + kart 0.26.0 |
| `relay-altare.py` | Cent AI relay, key from env, loopback only |
| `health.py` | `/health` server on `$PORT` |
| `entrypoint.sh` | NO_PROXY sanitize, writes `.env`, seeds state, starts relay + health, execs gateway |
| `config.yaml` | Hermes config (dummy placeholder key only) |
| `pairing/telegram-approved.json` | Pairing seed for user 1385201625 (no secret) |
| `skills/binance-agentic-wallet/` | The only skill, exact copy of the VM's (20 files) |
| `kart-cli/` | kart 0.26.0 self-contained scripts (`kart.mjs`, `guard.mjs`, `update.mjs`, `release.json`) |
| `.dockerignore` | Excludes `.env`, keys, caches |
