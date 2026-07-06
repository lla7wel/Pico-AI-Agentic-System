"""Runtime settings: everything the dashboard controls.

Values are stored JSON-encoded in the `settings` table and cached in memory
(settings are read on every voice turn). Secrets are stored as-is but never
returned to the client in full — see masked_all().
"""
import json
from typing import Any

from . import db

# --- Defaults. Anything not in the DB falls back to these. ----------------
DEFAULTS: dict[str, Any] = {
    # LLM (OpenAI). Model is chosen in the dashboard, not hardcoded.
    "llm_provider": "openai",
    "openai_api_key": "",
    "openai_base_url": "",              # blank = api.openai.com; set for proxies/Azure-compatible
    "openai_model": "gpt-4o-mini",
    "temperature": 0.7,
    "max_tokens": 300,

    # Response shaping for the tiny screen.
    "system_prompt": (
        "You are a retro terminal voice assistant shown on a tiny "
        "green-phosphor screen with no scrolling. Answer in plain English "
        "only. Be direct and useful. Keep replies under 400 characters. No "
        "markdown, lists, emoji, or code blocks — just short plain sentences."
    ),
    "max_response_chars": 400,

    # Speech-to-text (Deepgram).
    "deepgram_api_key": "",
    "deepgram_model": "nova-3",
    "sample_rate": 16000,

    # Agent behaviour.
    "history_turns": 10,

    # Per-integration enable/authorize state, keyed by tool name:
    #   {"email_read": {"enabled": false, "authorized": false}, ...}
    "integrations": {},

    # Dashboard admin (password hash + salt live here; never returned).
    "admin_password_hash": "",
    "admin_password_salt": "",
    "admin_password_is_default": True,
}

# Keys whose value must never be sent to the browser in full.
SECRET_KEYS = {
    "openai_api_key",
    "deepgram_api_key",
    "admin_password_hash",
    "admin_password_salt",
}

# Secrets that the dashboard shows a masked hint for (the rest are hidden).
HINTED_SECRETS = {"openai_api_key", "deepgram_api_key"}

_cache: dict[str, Any] = {}


async def load() -> None:
    """Populate the in-memory cache from the DB. Call once at startup."""
    _cache.clear()
    _cache.update(DEFAULTS)
    rows = await db.fetchall("SELECT key, value FROM settings")
    for r in rows:
        try:
            _cache[r["key"]] = json.loads(r["value"])
        except (json.JSONDecodeError, TypeError):
            pass


def get(key: str, default: Any = None) -> Any:
    if key in _cache:
        return _cache[key]
    return DEFAULTS.get(key, default)


async def set_many(updates: dict[str, Any]) -> None:
    """Persist and cache a batch of settings. Unknown keys are ignored to
    keep the store to a known shape. Empty-string secret values are treated
    as 'leave unchanged' so the masked UI never wipes a stored key."""
    for key, value in updates.items():
        if key not in DEFAULTS:
            continue
        if key in SECRET_KEYS and value == "":
            continue  # don't overwrite a stored secret with a blank field
        _cache[key] = value
        await db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )


def _mask(value: str) -> str | None:
    if not value:
        return None
    tail = value[-4:] if len(value) >= 4 else value
    return f"…{tail}"


def masked_all() -> dict[str, Any]:
    """Full settings for the dashboard, with secrets masked. Secret fields
    become {"set": bool, "hint": "…abcd"} instead of the raw value."""
    out: dict[str, Any] = {}
    for key in DEFAULTS:
        if key in SECRET_KEYS:
            if key in HINTED_SECRETS:
                val = get(key)
                out[key] = {"set": bool(val), "hint": _mask(val)}
            # password hash/salt: not exposed at all
            continue
        out[key] = get(key)
    out["admin_password_is_default"] = get("admin_password_is_default")
    return out


def export_config(include_secrets: bool) -> dict[str, Any]:
    """Config snapshot for export. Password hash/salt are never exported."""
    out = {}
    for key in DEFAULTS:
        if key in ("admin_password_hash", "admin_password_salt",
                   "admin_password_is_default"):
            continue
        if key in SECRET_KEYS and not include_secrets:
            continue
        out[key] = get(key)
    return out
