# Pico W Retro Voice Agent

A push-to-talk voice assistant. A Raspberry Pi Pico W captures speech through
a direct-plugged I2S mic, streams it live to a cloud backend, which transcribes
it (Deepgram), asks Claude with conversation memory, and streams the text answer
back to a green-phosphor CRT-style terminal on the Pico's TFT. No speaker —
text only. Nothing persists on the device; all memory lives server-side.

```
[Pico W] --WSS/PCM--> [Fly.io backend] --> Deepgram STT --> Claude --> SQLite
   TFT  <---text------      (raw audio forwarded live, never written to disk)
```

## Repo layout
- **[`backend/`](backend/)** — FastAPI WebSocket server (Deepgram → Claude →
  SQLite), Docker + Fly.io. Start with [`backend/DEPLOY.md`](backend/DEPLOY.md).
- **[`firmware/`](firmware/)** — Arduino sketch for the Pico W (custom PIO I2S
  receiver, WSS client, terminal UI). Start with [`firmware/README.md`](firmware/README.md).

## Build order (see brief §7)
1. **Backend, locally.** `backend/DEPLOY.md` §1 — stream a WAV through the full
   pipeline with `test_client.py` before touching hardware. An offline
   integration test with Deepgram/Claude stubbed is in
   `backend/test_flow_mock.py` (`python test_flow_mock.py`, no keys needed).
2. **Deploy the backend** to Fly.io and confirm the `wss://` endpoint is
   reachable and auth-gated (`DEPLOY.md` §2–6).
3. **Firmware:** WiFi + TFT boot animation first, then validate the PIO I2S
   receiver in isolation (serial dump), then TLS, then the full flow, then the
   LED/buzzer. Full procedure in `firmware/README.md`.

## What you supply (brief §8)
Anthropic API key · Deepgram API key · WiFi SSID/password · a Fly.io account ·
one shared secret string used as `PICO_AUTH_TOKEN` in **both** the backend
`.env`/Fly secrets and the firmware `secrets.h`.

## Status
- **Backend:** complete and verified offline (auth, multi-turn memory, live PCM
  forwarding, persistence, and bad-auth rejection all pass in
  `test_flow_mock.py`). Needs real API keys + `fly deploy` to go live.
- **Firmware:** complete; the PIO instruction encodings are machine-verified.
  The mic sample tuning and TLS must be validated on hardware per the bring-up
  steps — those are the two flagged risk areas (brief §9) and can't be tested
  without the board.
