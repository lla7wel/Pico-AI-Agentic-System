"""SQLite access layer (aiosqlite). Schema + small generic helpers.

Tables:
  settings       key/value runtime config (incl. masked secrets)
  devices        Pico devices + their auth tokens + last-seen
  conversations  per-device transcript/reply text (no audio ever)
  events         durable device/error/turn events for the dashboard
"""
import os
import aiosqlite

from .config import SQLITE_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL              -- JSON-encoded
);

CREATE TABLE IF NOT EXISTS devices (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  device_id  TEXT UNIQUE NOT NULL,
  name       TEXT NOT NULL DEFAULT '',
  token      TEXT UNIQUE NOT NULL,
  wifi_ssid  TEXT NOT NULL DEFAULT '',   -- stored for reference / future OTA
  last_seen  TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversations (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  device_id  TEXT NOT NULL,
  role       TEXT NOT NULL,        -- 'user' or 'assistant'
  content    TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_conv_device ON conversations (device_id, id);

CREATE TABLE IF NOT EXISTS events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  level      TEXT NOT NULL,        -- info | warn | error
  category   TEXT NOT NULL,        -- system | device | stt | llm | tool
  device_id  TEXT,
  message    TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_events_time ON events (id DESC);
"""


def _connect():
    return aiosqlite.connect(SQLITE_PATH)


async def init_db() -> None:
    parent = os.path.dirname(SQLITE_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    async with _connect() as db:
        await db.executescript(_SCHEMA)
        await db.commit()


async def fetchall(sql: str, params: tuple = ()):
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(sql, params)
        return await cur.fetchall()


async def fetchone(sql: str, params: tuple = ()):
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(sql, params)
        return await cur.fetchone()


async def execute(sql: str, params: tuple = ()) -> int:
    """Run a write and return lastrowid."""
    async with _connect() as db:
        cur = await db.execute(sql, params)
        await db.commit()
        return cur.lastrowid
