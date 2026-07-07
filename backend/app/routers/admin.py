"""Admin/dashboard REST API. Everything the dashboard controls lives here.

All routes except /api/login require a valid admin bearer token (see
security.require_admin). Secrets are never returned in full.
"""
import re
import secrets as _secrets
import time

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query

from .. import db, settings_store, presence, security, stt
from .. import llm
from ..logbuf import read_logs, read_events
from ..tools import registry

router = APIRouter(prefix="/api")
STARTED = time.time()
VERSION = "2.0"

admin = Depends(security.require_admin)


# ---- Auth ----------------------------------------------------------------
@router.post("/login")
async def login(body: dict = Body(...)):
    if not security.verify_password(body.get("password", "")):
        raise HTTPException(401, "wrong password")
    token = security.create_session()
    return {"token": token,
            "must_change": bool(settings_store.get("admin_password_is_default"))}


@router.post("/logout", dependencies=[admin])
async def logout(authorization: str = Header(default="")):
    if authorization.lower().startswith("bearer "):
        security.destroy_session(authorization[7:])
    return {"ok": True}


@router.get("/session", dependencies=[admin])
async def session():
    return {"ok": True,
            "must_change": bool(settings_store.get("admin_password_is_default"))}


@router.post("/password", dependencies=[admin])
async def change_password(body: dict = Body(...)):
    await security.set_admin_password(body.get("new_password", ""))
    return {"ok": True}


# ---- Status --------------------------------------------------------------
@router.get("/status", dependencies=[admin])
async def status():
    return {
        "version": VERSION,
        "uptime_seconds": int(time.time() - STARTED),
        "online_devices": presence.online_count(),
        "providers": {
            "openai_configured": bool(settings_store.get("openai_api_key")),
            "deepgram_configured": bool(settings_store.get("deepgram_api_key")),
            "model": settings_store.get("openai_model"),
            "llm_provider": settings_store.get("llm_provider"),
        },
    }


# ---- Settings ------------------------------------------------------------
@router.get("/settings", dependencies=[admin])
async def get_settings():
    return settings_store.masked_all()


@router.put("/settings", dependencies=[admin])
async def put_settings(body: dict = Body(...)):
    # admin_password_* are managed via /password only.
    body = {k: v for k, v in body.items()
            if not k.startswith("admin_password")}
    await settings_store.set_many(body)
    return settings_store.masked_all()


@router.get("/config/export", dependencies=[admin])
async def export_config(include_secrets: bool = Query(False)):
    return {
        "version": VERSION,
        "settings": settings_store.export_config(include_secrets),
    }


@router.post("/config/import", dependencies=[admin])
async def import_config(body: dict = Body(...)):
    cfg = body.get("settings", body)
    await settings_store.set_many(cfg)
    return settings_store.masked_all()


# ---- Provider connection tests -------------------------------------------
@router.post("/test/openai", dependencies=[admin])
async def test_openai():
    try:
        return await llm.test_provider()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


@router.post("/test/deepgram", dependencies=[admin])
async def test_deepgram():
    try:
        return await stt.test_deepgram()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


# ---- Devices -------------------------------------------------------------
def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9-]+", "-", (text or "").lower()).strip("-")
    return s or "pico"


def _device_view(row) -> dict:
    p = presence.get(row["device_id"]) or {}
    return {
        "device_id": row["device_id"],
        "name": row["name"],
        "wifi_ssid": row["wifi_ssid"],
        "token_hint": f"…{row['token'][-4:]}" if row["token"] else None,
        "last_seen": row["last_seen"],
        "created_at": row["created_at"],
        "online": bool(p.get("connected")),
        "remote": p.get("remote"),
    }


@router.get("/devices", dependencies=[admin])
async def list_devices():
    rows = await db.fetchall("SELECT * FROM devices ORDER BY id")
    return [_device_view(r) for r in rows]


@router.post("/devices", dependencies=[admin])
async def create_device(body: dict = Body(...)):
    name = body.get("name", "")
    device_id = body.get("device_id") or _slug(name) or f"pico-{_secrets.token_hex(2)}"
    if await db.fetchone("SELECT 1 FROM devices WHERE device_id = ?", (device_id,)):
        raise HTTPException(409, f"device_id '{device_id}' already exists")
    token = _secrets.token_urlsafe(24)
    await db.execute(
        "INSERT INTO devices (device_id, name, token, wifi_ssid) VALUES (?, ?, ?, ?)",
        (device_id, name, token, body.get("wifi_ssid", "")),
    )
    # Token returned in FULL exactly once, for pasting into secrets.h.
    return {"device_id": device_id, "name": name, "token": token}


@router.patch("/devices/{device_id}", dependencies=[admin])
async def update_device(device_id: str, body: dict = Body(...)):
    row = await db.fetchone("SELECT * FROM devices WHERE device_id = ?", (device_id,))
    if not row:
        raise HTTPException(404, "device not found")
    name = body.get("name", row["name"])
    wifi = body.get("wifi_ssid", row["wifi_ssid"])
    await db.execute("UPDATE devices SET name = ?, wifi_ssid = ? WHERE device_id = ?",
                     (name, wifi, device_id))
    return _device_view(await db.fetchone(
        "SELECT * FROM devices WHERE device_id = ?", (device_id,)))


@router.post("/devices/{device_id}/rotate", dependencies=[admin])
async def rotate_token(device_id: str):
    if not await db.fetchone("SELECT 1 FROM devices WHERE device_id = ?", (device_id,)):
        raise HTTPException(404, "device not found")
    token = _secrets.token_urlsafe(24)
    await db.execute("UPDATE devices SET token = ? WHERE device_id = ?",
                     (token, device_id))
    return {"device_id": device_id, "token": token}


@router.delete("/devices/{device_id}", dependencies=[admin])
async def delete_device(device_id: str):
    await db.execute("DELETE FROM devices WHERE device_id = ?", (device_id,))
    return {"ok": True}


# ---- Conversations -------------------------------------------------------
@router.get("/conversations", dependencies=[admin])
async def get_conversations(device_id: str | None = None, limit: int = 100):
    if device_id:
        rows = await db.fetchall(
            "SELECT device_id, role, content, created_at FROM conversations "
            "WHERE device_id = ? ORDER BY id DESC LIMIT ?", (device_id, limit))
    else:
        rows = await db.fetchall(
            "SELECT device_id, role, content, created_at FROM conversations "
            "ORDER BY id DESC LIMIT ?", (limit,))
    return [dict(r) for r in rows]


@router.delete("/conversations", dependencies=[admin])
async def clear_conversations(device_id: str | None = None):
    if device_id:
        await db.execute("DELETE FROM conversations WHERE device_id = ?", (device_id,))
    else:
        await db.execute("DELETE FROM conversations")
    return {"ok": True}


# ---- Logs & events -------------------------------------------------------
@router.get("/logs", dependencies=[admin])
async def get_logs(level: str | None = None, category: str | None = None,
                   device_id: str | None = None, limit: int = 200):
    return read_logs(level, category, device_id, limit)


@router.get("/events", dependencies=[admin])
async def get_events(level: str | None = None, category: str | None = None,
                     device_id: str | None = None, limit: int = 200):
    return await read_events(level, category, device_id, limit)


# ---- Integrations / tools ------------------------------------------------
@router.get("/integrations", dependencies=[admin])
async def list_integrations():
    return registry.list_all()


@router.patch("/integrations/{name}", dependencies=[admin])
async def update_integration(name: str, body: dict = Body(...)):
    return await registry.set_state(
        name, enabled=body.get("enabled"), authorized=body.get("authorized"))
