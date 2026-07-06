"""LLM entry point used by the voice pipeline.

Dispatches to the configured provider, builds the message list from stored
history + the fresh transcript, and trims the reply to the screen budget.
"""
import logging

from .base import LLMError
from .openai_provider import OpenAIProvider
from .. import settings_store

log = logging.getLogger("llm")

_PROVIDERS = {
    "openai": OpenAIProvider(),
}


def _provider():
    name = settings_store.get("llm_provider", "openai")
    provider = _PROVIDERS.get(name)
    if provider is None:
        raise LLMError(f"unknown llm_provider: {name}")
    return provider


async def generate_reply(device_id: str, history: list[dict],
                         transcript: str) -> str:
    provider = _provider()
    messages = list(history) + [{"role": "user", "content": transcript}]

    text = await provider.generate(
        system_prompt=settings_store.get("system_prompt"),
        messages=messages,
        model=settings_store.get("openai_model"),
        temperature=float(settings_store.get("temperature")),
        max_tokens=int(settings_store.get("max_tokens")),
        device_id=device_id,
    )

    limit = int(settings_store.get("max_response_chars"))
    if len(text) > limit:
        text = text[: limit - 3].rstrip() + "..."   # ASCII only for the TFT
    return text


async def test_provider() -> dict:
    return await _provider().test(settings_store.get("openai_model"))
