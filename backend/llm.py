"""Claude ("the brain"). Builds the message list from stored history +
the fresh transcript, calls the API, and returns a screen-sized reply.
"""
import logging

from anthropic import AsyncAnthropic

from config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    SYSTEM_PROMPT,
    MAX_RESPONSE_CHARS,
)

log = logging.getLogger("llm")

_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)


async def generate_reply(history: list[dict], transcript: str) -> str:
    """history is oldest-first [{role, content}, ...] from SQLite.
    transcript is the newly recognized user utterance.
    Returns Claude's reply, hard-trimmed to the display budget.
    """
    messages = list(history)
    messages.append({"role": "user", "content": transcript})

    # max_tokens is generous enough for ~400 chars; the system prompt and
    # the trim below are what actually keep it screen-sized.
    resp = await _client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=messages,
    )

    text = "".join(
        block.text for block in resp.content if block.type == "text"
    ).strip()

    if len(text) > MAX_RESPONSE_CHARS:
        # ASCII "..." only — the Pico terminal font has no ellipsis glyph.
        text = text[: MAX_RESPONSE_CHARS - 3].rstrip() + "..."
    log.info("Claude reply (%d chars)", len(text))
    return text
