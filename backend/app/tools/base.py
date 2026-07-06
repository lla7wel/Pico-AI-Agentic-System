"""Tool primitive shared by built-in tools and permission-gated integrations."""
from dataclasses import dataclass, field
from typing import Awaitable, Callable

# handler(args: dict, device_id: str | None) -> result (JSON-serializable)
Handler = Callable[[dict, "str | None"], Awaitable[object]]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict                       # JSON Schema for the arguments
    handler: Handler
    category: str = "builtin"              # builtin | integration
    # Integrations gate access behind an explicit authorization step (OAuth,
    # token, consent). Built-in safe tools leave this False.
    requires_auth: bool = False
    # Whether the integration is enabled by default (built-ins usually True).
    default_enabled: bool = True
    # Human note shown in the dashboard (e.g. what access it needs).
    note: str = ""

    def openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
