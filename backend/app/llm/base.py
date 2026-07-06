"""LLM provider interface.

Providers turn (system prompt, message history, available tools) into a text
reply, running any tool-calls the model requests against the tool registry.
Keeping this behind an interface means a second provider can be added later
without touching the voice pipeline.
"""
from typing import Protocol


class LLMError(Exception):
    pass


class LLMProvider(Protocol):
    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],   # [{role, content}, ...] chronological
        model: str,
        temperature: float,
        max_tokens: int,
        device_id: str | None,
    ) -> str:
        ...

    async def test(self, model: str) -> dict:
        """Cheap connectivity check. Returns {"ok": bool, "models": [...], ...}."""
        ...
