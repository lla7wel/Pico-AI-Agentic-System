"""Tool subsystem: registry + built-ins + integration scaffolding."""
from .builtin import register_builtins
from .integrations import register_integrations


def register_all() -> None:
    register_builtins()
    register_integrations()
