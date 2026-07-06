"""FastAPI WebSocket server for the Pico W retro voice agent.

One long-lived WebSocket per device carries many push-to-talk turns:

  client -> {"type":"auth","token":...,"device_id":...}   (once)
  client -> {"type":"start"}
  client -> <binary PCM frames> ...
  client -> {"type":"stop"}
  server -> {"type":"response","text":...}    (or {"type":"error",...})
  ... repeat start/stop for each turn ...

Raw audio is forwarded straight to Deepgram and never written to disk.
Only transcript + reply text are persisted (see db.py).
"""
import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

import db
from config import PICO_AUTH_TOKEN, HISTORY_TURNS
from stt import DeepgramStreamer
from llm import generate_reply

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("main")

app = FastAPI(title="Pico Voice Agent")


@app.on_event("startup")
async def _startup() -> None:
    await db.init_db()
    log.info("Database ready")


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


async def _send_json(ws: WebSocket, payload: dict) -> None:
    if ws.application_state == WebSocketState.CONNECTED:
        await ws.send_text(json.dumps(payload))


async def _send_error(ws: WebSocket, message: str) -> None:
    log.warning("-> error: %s", message)
    await _send_json(ws, {"type": "error", "message": message})


@app.websocket("/ws/voice")
async def voice(ws: WebSocket):
    await ws.accept()
    device_id = "pico-01"

    # --- Auth: first message must be a valid auth frame ----------------
    try:
        first = await ws.receive_text()
        msg = json.loads(first)
    except (WebSocketDisconnect, json.JSONDecodeError, RuntimeError):
        await ws.close(code=1008)
        return

    if msg.get("type") != "auth" or msg.get("token") != PICO_AUTH_TOKEN:
        await _send_error(ws, "auth failed")
        await ws.close(code=1008)
        return
    device_id = msg.get("device_id") or device_id
    log.info("Authenticated device %s", device_id)
    await _send_json(ws, {"type": "ready"})

    streamer: DeepgramStreamer | None = None
    recording = False

    try:
        while True:
            packet = await ws.receive()

            if packet.get("type") == "websocket.disconnect":
                break

            # --- Binary PCM frame: forward live to Deepgram ------------
            if packet.get("bytes") is not None:
                if recording and streamer is not None:
                    await streamer.send(packet["bytes"])
                continue

            # --- Text control frame ------------------------------------
            raw = packet.get("text")
            if raw is None:
                continue
            try:
                ctrl = json.loads(raw)
            except json.JSONDecodeError:
                await _send_error(ws, "bad json")
                continue

            mtype = ctrl.get("type")

            if mtype == "start":
                if recording:
                    continue  # already recording; ignore duplicate press
                try:
                    streamer = DeepgramStreamer()
                    await streamer.open()
                    recording = True
                    log.info("Recording started")
                except Exception as e:  # noqa: BLE001
                    streamer = None
                    log.exception("Failed to open STT")
                    await _send_error(ws, f"stt open failed: {e}")

            elif mtype == "stop":
                if not recording or streamer is None:
                    continue  # spurious stop; ignore
                recording = False
                await _handle_turn(ws, device_id, streamer)
                streamer = None

            elif mtype == "ping":
                await _send_json(ws, {"type": "pong"})

            else:
                await _send_error(ws, f"unknown message type: {mtype}")

    except WebSocketDisconnect:
        log.info("Device %s disconnected", device_id)
    except Exception:  # noqa: BLE001
        log.exception("Unexpected session error")
        await _send_error(ws, "internal error")
    finally:
        if streamer is not None:
            try:
                await streamer.finish()
            except Exception:  # noqa: BLE001
                pass


async def _handle_turn(
    ws: WebSocket, device_id: str, streamer: DeepgramStreamer
) -> None:
    """Finalize STT -> Claude -> persist -> send reply, for one turn."""
    # 1. Finalize transcript.
    try:
        transcript = await streamer.finish()
    except Exception as e:  # noqa: BLE001
        log.exception("STT finalize failed")
        await _send_error(ws, f"stt failed: {e}")
        return

    if not transcript:
        await _send_error(ws, "no speech detected")
        return
    log.info("Transcript: %s", transcript)

    # 2. Load memory + call Claude.
    try:
        history = await db.get_recent_turns(device_id, HISTORY_TURNS)
        reply = await generate_reply(history, transcript)
    except Exception as e:  # noqa: BLE001
        log.exception("LLM failed")
        await _send_error(ws, f"llm failed: {e}")
        return

    # 3. Persist both sides of the turn (text only).
    try:
        await db.add_turn(device_id, "user", transcript)
        await db.add_turn(device_id, "assistant", reply)
    except Exception:  # noqa: BLE001
        log.exception("DB write failed (continuing to answer)")

    # 4. Deliver the reply.
    await _send_json(ws, {"type": "response", "text": reply})
