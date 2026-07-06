"""Admin authentication (dashboard) and device-token validation (Pico).

Admin auth is a simple password login that mints an in-memory bearer token —
adequate for a single-user personal dashboard served over HTTPS. The password
itself is stored only as a PBKDF2 hash in the settings store.
"""
import hashlib
import os
import secrets
import time

from fastapi import Header, HTTPException

from . import db, settings_store
from .config import BOOTSTRAP_ADMIN_PASSWORD, SESSION_TTL_HOURS

# token -> expiry epoch seconds
_sessions: dict[str, float] = {}

_PBKDF_ROUNDS = 200_000


def _hash_password(password: str, salt: str) -> str:
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), _PBKDF_ROUNDS
    )
    return dk.hex()


async def _store_password(password: str, is_default: bool) -> None:
    salt = os.urandom(16).hex()
    await settings_store.set_many({
        "admin_password_salt": salt,
        "admin_password_hash": _hash_password(password, salt),
        "admin_password_is_default": is_default,
    })


async def ensure_admin_password() -> None:
    """Seed the admin password on first run from the bootstrap env value."""
    if not settings_store.get("admin_password_hash"):
        await _store_password(BOOTSTRAP_ADMIN_PASSWORD, is_default=True)


async def set_admin_password(new_password: str) -> None:
    if len(new_password) < 6:
        raise HTTPException(400, "password too short (min 6 chars)")
    await _store_password(new_password, is_default=False)


def verify_password(password: str) -> bool:
    salt = settings_store.get("admin_password_salt")
    stored = settings_store.get("admin_password_hash")
    if not salt or not stored:
        return False
    candidate = _hash_password(password, salt)
    return secrets.compare_digest(candidate, stored)


def create_session() -> str:
    token = secrets.token_urlsafe(32)
    _sessions[token] = time.time() + SESSION_TTL_HOURS * 3600
    return token


def destroy_session(token: str) -> None:
    _sessions.pop(token, None)


def _valid_session(token: str) -> bool:
    exp = _sessions.get(token)
    if exp is None:
        return False
    if time.time() > exp:
        _sessions.pop(token, None)
        return False
    return True


async def require_admin(authorization: str = Header(default="")) -> None:
    """FastAPI dependency guarding every /api admin route."""
    token = ""
    if authorization.lower().startswith("bearer "):
        token = authorization[7:]
    if not _valid_session(token):
        raise HTTPException(401, "not authenticated")


# ---- Device tokens (Pico auth) -------------------------------------------
async def device_for_token(token: str):
    """Return the device row matching a token, or None."""
    if not token:
        return None
    return await db.fetchone(
        "SELECT * FROM devices WHERE token = ?", (token,)
    )
