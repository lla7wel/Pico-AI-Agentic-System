# Pico W Voice Terminal + Agent Platform

A personal agentic AI system. A Raspberry Pi Pico W is a **thin voice terminal**
— it captures speech, streams it to the backend, and displays the reply on a
green-phosphor CRT-style TFT. All the intelligence lives in the **backend**,
which is an **agent platform** configured entirely through a web dashboard.

```
[Pico W: I/O only]                 [Backend: the brain / agent platform]
  capture voice ──WSS/PCM──▶  Deepgram STT ─▶ OpenAI (LLM + tool-calling) ─▶ reply
  show reply    ◀───text────                 │
  status LED/buzzer                          ├─ runtime config in SQLite (no .env editing)
                                             ├─ web dashboard: keys, model, prompt,
                                             │   devices, logs, history, integrations
                                             └─ permission-gated integrations (email,
                                                 calendar, files, web) — off by default
```

The Pico stays a dumb terminal: no keys, no memory, no agent logic on-device.
Everything is managed from the dashboard.

## Repo layout
- **[`backend/`](backend/)** — FastAPI agent platform: voice WebSocket + admin
  API + dashboard SPA. Start with [`backend/DEPLOY.md`](backend/DEPLOY.md).
- **[`firmware/`](firmware/)** — Arduino sketch for the Pico W. **Unchanged** by
  the platform pivot; the only thing you touch is pasting a dashboard-generated
  device token into `secrets.h`. See [`firmware/README.md`](firmware/README.md).

## The dashboard
Served at `/` by the backend (log in with the admin password). From there you:
enter/update OpenAI + Deepgram keys · choose the OpenAI model · edit the system
prompt · tune response length & behavior · manage device tokens · view
conversation history (and clear it) · test OpenAI/Deepgram connectivity · watch
logs & events · see device online/offline status · enable/authorize integrations
· export/import config. **No source, `.env`, or config-file editing required.**

## Architecture highlights
- **LLM = OpenAI**, behind a provider interface (`app/llm/`) with function/
  tool-calling support. Model is dashboard-configurable, never hardcoded.
- **STT = Deepgram** streaming (kept — it finalizes the transcript by the time
  the button is released), key pulled from settings at runtime.
- **Runtime config store** (`app/settings_store.py`) in SQLite; secrets masked
  on read, and a blank field never wipes a stored key.
- **Tool/integration framework** (`app/tools/`): safe built-ins on by default;
  email/calendar/reminders/files/web are scaffolded, **off by default, and
  require explicit enable + authorize** before the model can use them. No unsafe
  automatic access.
- **Observability**: in-memory log tail + durable events table, device presence,
  per-device conversation history — all surfaced in the dashboard.
- **Pico protocol unchanged** — existing firmware works as-is.

## Status
- **Backend:** complete and verified offline — `backend/test_flow_mock.py`
  passes (admin auth + password change, masked secrets, device token gating,
  a full stubbed voice turn, persistence, presence, integration
  enable/authorize gating, events/logs, config export with secret opt-in). The
  dashboard was loaded in a browser and renders/works with no console errors.
  Add real keys via the dashboard + `fly deploy` to go live.
- **Firmware:** unchanged from the initial build (PIO I2S encodings machine-
  verified; mic tuning + TLS still need on-hardware validation per
  `firmware/README.md`). Only new step: paste the dashboard device token into
  `secrets.h`.

## What you supply
An OpenAI API key · a Deepgram API key · WiFi SSID/password (in `secrets.h`) ·
a Fly.io account · an admin password for the dashboard. All entered via the
dashboard except WiFi (compile-time on the Pico) and the bootstrap admin
password.
