"""Persistent conversation memory backed by SQLite (aiosqlite).

Only text is ever stored here — transcripts and Claude's replies. Raw
audio never touches disk. The DB file lives on the Fly.io persistent
volume (SQLITE_PATH) so history survives restarts.
"""
import os
import aiosqlite

from config import SQLITE_PATH, HISTORY_TURNS

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  device_id TEXT NOT NULL,
  role TEXT NOT NULL,        -- 'user' or 'assistant'
  content TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_device_created
  ON conversations (device_id, created_at);
"""


async def init_db() -> None:
    """Create the schema if needed. Call once at startup."""
    parent = os.path.dirname(SQLITE_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    async with aiosqlite.connect(SQLITE_PATH) as db:
        await db.executescript(_SCHEMA)
        await db.commit()


async def add_turn(device_id: str, role: str, content: str) -> None:
    """Append a single conversation row."""
    async with aiosqlite.connect(SQLITE_PATH) as db:
        await db.execute(
            "INSERT INTO conversations (device_id, role, content) "
            "VALUES (?, ?, ?)",
            (device_id, role, content),
        )
        await db.commit()


async def get_recent_turns(device_id: str, limit: int = HISTORY_TURNS):
    """Return the last `limit` turns for a device, oldest-first, as a
    list of {"role": ..., "content": ...} dicts ready for the Claude API.
    """
    async with aiosqlite.connect(SQLITE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT role, content FROM conversations "
            "WHERE device_id = ? ORDER BY id DESC LIMIT ?",
            (device_id, limit),
        )
        rows = await cursor.fetchall()
    # Fetched newest-first; reverse to chronological order for the LLM.
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
