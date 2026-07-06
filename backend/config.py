"""Central configuration, loaded once from environment variables.

All secrets and tunables live here so the rest of the code never reads
os.environ directly. See .env.example for the full list.
"""
import os


def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            "See .env.example."
        )
    return val


# --- Secrets (required) -------------------------------------------------
ANTHROPIC_API_KEY = _require("ANTHROPIC_API_KEY")
DEEPGRAM_API_KEY = _require("DEEPGRAM_API_KEY")
PICO_AUTH_TOKEN = _require("PICO_AUTH_TOKEN")

# --- Tunables (have sane defaults) --------------------------------------
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
SQLITE_PATH = os.environ.get("SQLITE_PATH", "/data/conversations.db")

# Audio format the Pico streams (must match firmware).
SAMPLE_RATE = int(os.environ.get("SAMPLE_RATE", "16000"))

# How many prior turns (user+assistant rows) to feed Claude as memory.
HISTORY_TURNS = int(os.environ.get("HISTORY_TURNS", "10"))

# Keep replies short: no scrolling on the 480x320 TFT.
MAX_RESPONSE_CHARS = int(os.environ.get("MAX_RESPONSE_CHARS", "400"))

# System persona for Claude. Terse and screen-friendly.
SYSTEM_PROMPT = os.environ.get(
    "SYSTEM_PROMPT",
    (
        "You are a retro terminal voice assistant displayed on a tiny "
        "green-phosphor screen with no scrolling. Answer in plain English "
        "only. Be direct and useful. Keep every reply under 400 characters "
        "(a few short sentences at most). No markdown, no lists, no emoji, "
        "no code blocks — just plain sentences that fit a small display."
    ),
)
