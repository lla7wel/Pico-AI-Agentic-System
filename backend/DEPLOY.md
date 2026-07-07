# Deploy the backend to Fly.io

The backend is configured at **runtime through the web dashboard** — API
keys, model, prompt, device tokens, etc. are entered in the browser and stored
in SQLite, not in env vars. Deployment just stands up the container + volume.

## 0. Prerequisites
- A [Fly.io](https://fly.io) account and `flyctl` (`brew install flyctl`, then `fly auth login`).
- Your OpenAI API key and Deepgram API key (entered later, in the dashboard).

## 1. Run locally first (recommended)
```bash
cd backend
./run.sh          # creates the venv, installs deps, serves on :8080
```
Open http://localhost:8080, log in with the admin password, then:
1. **Providers & Keys** → paste your OpenAI + Deepgram keys, pick a model,
   click **Test** on each.
2. **Devices** → add a device; copy the generated `DEVICE_ID` + `PICO_AUTH_TOKEN`
   into the firmware `secrets.h`.
3. **Behavior** → adjust the system prompt / response length if you like.

Offline sanity check (no keys/network needed):
```bash
python test_flow_mock.py      # stubs OpenAI + Deepgram, exercises the whole flow
```

## 2. Launch the app (creates it, no deploy yet)
`fly.toml` already exists; decline the overwrite prompt.
```bash
cd backend
fly launch --no-deploy --copy-config --name pico-voice-agent --region iad
```

## 3. Create the persistent volume (holds the SQLite DB)
Match `[mounts].source` in `fly.toml` (`pico_data`) and the same region.
```bash
fly volumes create pico_data --region iad --size 1
```

## 4. Set the ONE bootstrap secret
Only the first-run admin password is a Fly secret; everything else is set in
the dashboard afterward.
```bash
fly secrets set ADMIN_PASSWORD='choose-a-strong-password'
```

## 5. Deploy
```bash
fly deploy
```

## 6. Configure via the dashboard
```bash
open https://pico-voice-agent.fly.dev/          # log in with ADMIN_PASSWORD
```
- Change the admin password (Config & Admin).
- Enter OpenAI + Deepgram keys, choose the model, run both connection tests.
- Create your device, copy its token into `secrets.h`, flash the Pico.

Health check: `curl https://pico-voice-agent.fly.dev/healthz` → `{"status":"ok"}`.

## Notes
- **Single machine on purpose** (`min_machines_running = 1`, `--workers 1`):
  the SQLite store, settings cache, presence, and sessions assume one process.
- **Secrets at rest.** Keys are stored in the SQLite DB on the Fly volume,
  gated behind admin login + HTTPS and masked when read back. This is the
  pragmatic personal-use tradeoff; the volume is not separately encrypted.
- **Already-flashed Pico?** If a device was flashed with a fixed token before
  the backend existed, set `PICO_AUTH_TOKEN=<that token>` as a Fly secret once;
  first boot seeds a `pico-01` device row so it keeps working. Remove the
  secret afterward and manage devices in the dashboard.
- Logs: `fly logs`. The dashboard's Logs/Events tabs show app-level detail.
