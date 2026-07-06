"""Permission-gated integration placeholders.

These define the SHAPE of future agent capabilities (email, calendar, files,
web automation) so the dashboard can list them and so wiring a real
implementation later is a drop-in. Every one is:
  * off by default (default_enabled=False),
  * requires_auth=True (won't run until you authorize it in the dashboard),
  * currently a stub that returns a "not implemented" notice.

To make one real later: implement its handler (OAuth/token flow + API call)
and flip default behaviour as desired. The registry gating does not change.
"""
from .base import Tool
from . import registry


def _stub(capability: str):
    async def handler(args: dict, device_id):
        return {
            "status": "not_implemented",
            "capability": capability,
            "detail": (
                "This integration is scaffolded but not yet implemented. "
                "Authorize + implement it in a future update."
            ),
        }
    return handler


_INTEGRATIONS = [
    Tool(
        name="email_read",
        description="Read the user's recent emails (subject/sender/snippet).",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "optional search filter"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": [],
        },
        handler=_stub("email"),
        category="integration",
        requires_auth=True,
        default_enabled=False,
        note="Future: read-only email via OAuth. Requires explicit authorization.",
    ),
    Tool(
        name="calendar_read",
        description="List upcoming calendar events.",
        parameters={
            "type": "object",
            "properties": {"days_ahead": {"type": "integer", "default": 7}},
            "required": [],
        },
        handler=_stub("calendar"),
        category="integration",
        requires_auth=True,
        default_enabled=False,
        note="Future: read-only calendar via OAuth. Requires authorization.",
    ),
    Tool(
        name="reminders_manage",
        description="Create or list reminders / assignments for the user.",
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "create"]},
                "title": {"type": "string"},
                "due": {"type": "string", "description": "ISO datetime"},
            },
            "required": ["action"],
        },
        handler=_stub("reminders"),
        category="integration",
        requires_auth=True,
        default_enabled=False,
        note="Future: task/reminder store owned by the backend.",
    ),
    Tool(
        name="files_read",
        description="Read from authorized documents/files.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        handler=_stub("files"),
        category="integration",
        requires_auth=True,
        default_enabled=False,
        note="Future: scoped file/document access. Requires authorization.",
    ),
    Tool(
        name="web_task",
        description="Perform a web lookup or browser automation task.",
        parameters={
            "type": "object",
            "properties": {"instruction": {"type": "string"}},
            "required": ["instruction"],
        },
        handler=_stub("web"),
        category="integration",
        requires_auth=True,
        default_enabled=False,
        note="Future: web/browser automation. Requires authorization.",
    ),
]


def register_integrations() -> None:
    for tool in _INTEGRATIONS:
        registry.register(tool)
