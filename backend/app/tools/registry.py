"""Tool registry: what the agent can do, and what's turned on.

State model per tool:
  enabled     — offered to the model and executable (dashboard toggle)
  authorized  — only meaningful when requires_auth; the permission grant

Only tools that are enabled AND (not requires_auth OR authorized) are exposed
to the LLM. Integrations are off by default, so no external access happens
until you explicitly enable + authorize them.
"""
import logging

from .base import Tool
from .. import settings_store

log = logging.getLogger("tools")

_tools: dict[str, Tool] = {}


def register(tool: Tool) -> None:
    _tools[tool.name] = tool


def _state(name: str) -> dict:
    tool = _tools[name]
    saved = settings_store.get("integrations", {}) or {}
    s = saved.get(name, {})
    return {
        "enabled": s.get("enabled", tool.default_enabled),
        "authorized": s.get("authorized", False),
    }


def _is_active(name: str) -> bool:
    tool = _tools[name]
    st = _state(name)
    if not st["enabled"]:
        return False
    if tool.requires_auth and not st["authorized"]:
        return False
    return True


def openai_schemas() -> list[dict]:
    return [t.openai_schema() for n, t in _tools.items() if _is_active(n)]


async def execute(name: str, args: dict, device_id):
    tool = _tools.get(name)
    if tool is None:
        return {"error": f"unknown tool: {name}"}
    if not _is_active(name):
        return {"error": f"tool '{name}' is not enabled/authorized"}
    try:
        return await tool.handler(args, device_id)
    except Exception as e:  # noqa: BLE001
        log.exception("tool %s failed", name)
        return {"error": str(e)}


def list_all() -> list[dict]:
    """Dashboard view of every registered tool + its state."""
    out = []
    for name, tool in _tools.items():
        st = _state(name)
        out.append({
            "name": name,
            "description": tool.description,
            "category": tool.category,
            "requires_auth": tool.requires_auth,
            "note": tool.note,
            "enabled": st["enabled"],
            "authorized": st["authorized"],
            "active": _is_active(name),
        })
    return out


async def set_state(name: str, enabled: bool | None = None,
                    authorized: bool | None = None) -> dict:
    if name not in _tools:
        return {"error": "unknown tool"}
    saved = dict(settings_store.get("integrations", {}) or {})
    cur = dict(saved.get(name, {}))
    if enabled is not None:
        cur["enabled"] = bool(enabled)
    if authorized is not None:
        cur["authorized"] = bool(authorized)
    saved[name] = cur
    await settings_store.set_many({"integrations": saved})
    return {"name": name, **_state(name), "active": _is_active(name)}
