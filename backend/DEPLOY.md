# Deploy the Pico Voice Agent backend to Fly.io

## 0. Prerequisites
- A [Fly.io](https://fly.io) account and `flyctl` installed (`brew install flyctl`, then `fly auth login`).
- Your `ANTHROPIC_API_KEY`, `DEEPGRAM_API_KEY`, and a chosen `PICO_AUTH_TOKEN`
  (any strong random string — it must match `secrets.h` on the Pico).

## 1. Test locally first (recommended)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Provide secrets for the local run:
export ANTHROPIC_API_KEY=sk-ant-...
export DEEPGRAM_API_KEY=...
export PICO_AUTH_TOKEN=my-shared-secret
export SQLITE_PATH=./conversations.db      # local file, not /data

uvicorn main:app --host 0.0.0.0 --port 8080

# In another terminal, stream a WAV through the full pipeline:
#   ffmpeg -i sample.m4a -ar 16000 -ac 1 -sample_fmt s16 speech.wav
python test_client.py speech.wav
```
You should see the transcript logged server-side and an `ASSISTANT` reply
printed by the client. That proves Deepgram -> Claude -> SQLite works.

## 2. Launch the app (creates it, does NOT deploy yet)
`fly.toml` already exists, so decline when asked to overwrite it.
```bash
cd backend
fly launch --no-deploy --copy-config --name pico-voice-agent --region iad
```
Pick a region near you; keep it consistent with `fly.toml`'s `primary_region`.

## 3. Create the persistent volume (holds the SQLite DB)
Must match `[mounts].source` in `fly.toml` (`pico_data`) and the same region.
```bash
fly volumes create pico_data --region iad --size 1
```

## 4. Set secrets (never commit these)
```bash
fly secrets set \
  ANTHROPIC_API_KEY=sk-ant-... \
  DEEPGRAM_API_KEY=... \
  PICO_AUTH_TOKEN=my-shared-secret
```
`CLAUDE_MODEL`, `SQLITE_PATH`, etc. are non-secret and already in `fly.toml`.

## 5. Deploy
```bash
fly deploy
```

## 6. Verify
```bash
# Health check over HTTPS:
curl https://pico-voice-agent.fly.dev/healthz      # -> {"status":"ok"}

# Full round trip over WSS against the deployed app:
python test_client.py speech.wav \
  --url wss://pico-voice-agent.fly.dev/ws/voice \
  --token my-shared-secret
```

Your Pico's `secrets.h` then uses:
```
WS_HOST = "pico-voice-agent.fly.dev"
WS_PORT = 443
PICO_AUTH_TOKEN = "my-shared-secret"
```

## Notes
- **Single machine on purpose.** SQLite + in-memory per-connection session
  state assume one process (`min_machines_running = 1`, `--workers 1`).
- **Deepgram bills per streamed second.** A stuck socket (missed `stop`)
  keeps billing; watch usage during testing.
- Logs: `fly logs`. SSH in: `fly ssh console`. The DB is at `/data/conversations.db`.
