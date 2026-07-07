"""FastAPI application assembly for the Pico agent platform.

  /ws/voice   Pico-facing WebSocket
  /api/*      admin/dashboard REST API (auth-gated)
  /healthz    public health check
  /           the web dashboard (static SPA)
"""
import logging
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import db, settings_store, security, logbuf, tools
from .config import LEGACY_PICO_AUTH_TOKEN
from .routers import voice, admin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("main")

app = FastAPI(title="Pico Agent Platform")


async def _seed_legacy_device() -> None:
    """If an already-flashed Pico used PICO_AUTH_TOKEN, seed a device row so it
    keeps working after the upgrade. Runs only when there are no devices yet."""
    if not LEGACY_PICO_AUTH_TOKEN:
        return
    existing = await db.fetchone("SELECT COUNT(*) AS n FROM devices")
    if existing and existing["n"] == 0:
        await db.execute(
            "INSERT INTO devices (device_id, name, token) VALUES (?, ?, ?)",
            ("pico-01", "Legacy Pico", LEGACY_PICO_AUTH_TOKEN),
        )
        log.info("Seeded legacy device pico-01 from PICO_AUTH_TOKEN")


@app.on_event("startup")
async def _startup() -> None:
    logbuf.install()
    await db.init_db()
    await settings_store.load()
    await security.ensure_admin_password()
    await _seed_legacy_device()
    tools.register_all()
    log.info("Startup complete (agent platform %s)", admin.VERSION)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


app.include_router(voice.router)
app.include_router(admin.router)

# Serve the dashboard SPA last so explicit routes above win. html=True serves
# index.html at "/".
_static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/", StaticFiles(directory=_static_dir, html=True), name="dashboard")
