"""Safe built-in tools. Enabled by default; no external access, no auth."""
from datetime import datetime, timezone

from .base import Tool
from . import registry


async def _get_current_time(args: dict, device_id):
    tz = timezone.utc
    now = datetime.now(tz)
    return {"iso": now.isoformat(), "unix": int(now.timestamp())}


def register_builtins() -> None:
    registry.register(Tool(
        name="get_current_time",
        description="Get the current date and time (UTC).",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=_get_current_time,
        category="builtin",
        requires_auth=False,
        default_enabled=True,
        note="Local, safe. No external access.",
    ))
