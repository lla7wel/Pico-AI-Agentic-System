"""Pico-facing voice WebSocket. Wire protocol is UNCHANGED from v1, so the
existing firmware works without modification:

  client -> {"type":"auth","token":...,"device_id":...}
  server -> {"type":"ready"} | {"type":"error",...}
  client -> {"type":"start"} , binary PCM frames..., {"type":"stop"}
  server -> {"type":"response","text":...} | {"type":"error",...}

What changed underneath: the token is validated against the devices table,
presence is tracked, transcripts/replies persist per device, OpenAI (not
Anthropic) generates the reply, and everything is configured at runtime.
"""
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from .. import db, presence, settings_store, security
from ..logbuf import log_event
from ..stt import DeepgramStreamer
from ..llm import generate_reply

log = logging.getLogger("voice")
router = APIRouter()


async def _get_history(device_id: str, limit: int):
    rows = await db.fetchall(
        "SELECT role, content FROM conversations WHERE device_id = ? "
        "ORDER BY id DESC LIMIT ?",
        (device_id, limit),
    )
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


async def _add_turn(device_id: str, role: str, content: str) -> None:
    await db.execute(
        "INSERT INTO conversations (device_id, role, content) VALUES (?, ?, ?)",
        (device_id, role, content),
    )


async def _touch_device(device_id: str) -> None:
    await db.execute(
        "UPDATE devices SET last_seen = CURRENT_TIMESTAMP WHERE device_id = ?",
        (device_id,),
    )


async def _send_json(ws: WebSocket, payload: dict) -> None:
    if ws.application_state == WebSocketState.CONNECTED:
        await ws.send_text(json.dumps(payload))


async def _send_error(ws: WebSocket, message: str, device_id=None) -> None:
    log.warning("-> error: %s", message, extra={"category": "device",
                                                 "device_id": device_id})
    await log_event("error", "device", message, device_id)
    await _send_json(ws, {"type": "error", "message": message})


@router.websocket("/ws/voice")
async def voice(ws: WebSocket):
    await ws.accept()
    remote = ws.client.host if ws.client else "?"

    # --- Auth ---------------------------------------------------------------
    try:
        first = json.loads(await ws.receive_text())
    except (WebSocketDisconnect, json.JSONDecodeError, RuntimeError):
        await ws.close(code=1008)
        return

    device = None
    if first.get("type") == "auth":
        device = await security.device_for_token(first.get("token", ""))
    if device is None:
        await _send_error(ws, "auth failed")
        await ws.close(code=1008)
        return

    device_id = device["device_id"]
    presence.mark_connected(device_id, remote)
    await _touch_device(device_id)
    await log_event("info", "device", f"connected from {remote}", device_id)
    log.info("Device %s authenticated", device_id,
             extra={"category": "device", "device_id": device_id})
    await _send_json(ws, {"type": "ready"})

    streamer: DeepgramStreamer | None = None
    recording = False

    try:
        while True:
            packet = await ws.receive()
            if packet.get("type") == "websocket.disconnect":
                break

            if packet.get("bytes") is not None:
                if recording and streamer is not None:
                    await streamer.send(packet["bytes"])
                continue

            raw = packet.get("text")
            if raw is None:
                continue
            try:
                ctrl = json.loads(raw)
            except json.JSONDecodeError:
                await _send_error(ws, "bad json", device_id)
                continue

            mtype = ctrl.get("type")
            if mtype == "start":
                if recording:
                    continue
                try:
                    streamer = DeepgramStreamer()
                    await streamer.open()
                    recording = True
                    presence.touch(device_id)
                    log.info("Recording started", extra={"category": "device",
                                                          "device_id": device_id})
                except Exception as e:  # noqa: BLE001
                    streamer = None
                    log.exception("STT open failed")
                    await _send_error(ws, f"stt open failed: {e}", device_id)

            elif mtype == "stop":
                if not recording or streamer is None:
                    continue
                recording = False
                await _handle_turn(ws, device_id, streamer)
                streamer = None

            elif mtype == "ping":
                presence.touch(device_id)
                await _send_json(ws, {"type": "pong"})

            else:
                await _send_error(ws, f"unknown message type: {mtype}", device_id)

    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        log.exception("Voice session error")
    finally:
        if streamer is not None:
            try:
                await streamer.finish()
            except Exception:  # noqa: BLE001
                pass
        presence.mark_disconnected(device_id)
        await _touch_device(device_id)
        await log_event("info", "device", "disconnected", device_id)


async def _handle_turn(ws: WebSocket, device_id: str, streamer) -> None:
    try:
        transcript = await streamer.finish()
    except Exception as e:  # noqa: BLE001
        log.exception("STT finalize failed")
        await _send_error(ws, f"stt failed: {e}", device_id)
        return

    if not transcript:
        await _send_error(ws, "no speech detected", device_id)
        return
    log.info("Transcript: %s", transcript,
             extra={"category": "stt", "device_id": device_id})

    try:
        limit = int(settings_store.get("history_turns"))
        history = await _get_history(device_id, limit)
        reply = await generate_reply(device_id, history, transcript)
    except Exception as e:  # noqa: BLE001
        log.exception("LLM failed")
        await _send_error(ws, f"llm failed: {e}", device_id)
        return

    try:
        await _add_turn(device_id, "user", transcript)
        await _add_turn(device_id, "assistant", reply)
    except Exception:  # noqa: BLE001
        log.exception("DB write failed (still answering)")

    presence.touch(device_id)
    log.info("Reply (%d chars)", len(reply),
             extra={"category": "llm", "device_id": device_id})
    await _send_json(ws, {"type": "response", "text": reply})
