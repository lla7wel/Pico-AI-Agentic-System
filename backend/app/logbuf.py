"""Observability for the dashboard.

Two layers:
  * LOG_RING  — in-memory tail of ALL log records (dashboard "Logs" live view),
    fed by a logging.Handler so ordinary log.* calls show up automatically.
  * events()  — durable device/error/turn events written to the `events` table
    (dashboard "Events" / "Errors" history, survives restarts).
"""
import logging
import time
from collections import deque

from . import db
from .config import LOG_RING_SIZE

# ---- In-memory log tail --------------------------------------------------
LOG_RING: deque[dict] = deque(maxlen=LOG_RING_SIZE)


class RingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            LOG_RING.append({
                "ts": record.created,
                "level": record.levelname.lower(),
                "category": getattr(record, "category", record.name),
                "device_id": getattr(record, "device_id", None),
                "message": record.getMessage(),
            })
        except Exception:  # never let logging crash the app
            pass


def install() -> None:
    """Attach the ring handler to the root logger. Call once at startup."""
    root = logging.getLogger()
    if not any(isinstance(h, RingHandler) for h in root.handlers):
        root.addHandler(RingHandler())


def read_logs(level: str | None = None, category: str | None = None,
              device_id: str | None = None, limit: int = 200) -> list[dict]:
    items = list(LOG_RING)
    if level:
        items = [x for x in items if x["level"] == level]
    if category:
        items = [x for x in items if category in (x["category"] or "")]
    if device_id:
        items = [x for x in items if x["device_id"] == device_id]
    return items[-limit:][::-1]  # newest first


# ---- Durable events ------------------------------------------------------
async def log_event(level: str, category: str, message: str,
                    device_id: str | None = None) -> None:
    await db.execute(
        "INSERT INTO events (level, category, device_id, message) "
        "VALUES (?, ?, ?, ?)",
        (level, category, device_id, message),
    )


async def read_events(level: str | None = None, category: str | None = None,
                      device_id: str | None = None, limit: int = 200):
    clauses, params = [], []
    if level:
        clauses.append("level = ?"); params.append(level)
    if category:
        clauses.append("category = ?"); params.append(category)
    if device_id:
        clauses.append("device_id = ?"); params.append(device_id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    rows = await db.fetchall(
        f"SELECT level, category, device_id, message, created_at "
        f"FROM events {where} ORDER BY id DESC LIMIT ?",
        tuple(params),
    )
    return [dict(r) for r in rows]
