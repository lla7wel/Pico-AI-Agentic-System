"""OpenAI provider with function/tool-calling support.

The client is built per-call from the current settings, so an API-key or
model change in the dashboard takes effect on the very next turn — no restart.
"""
import json
import logging

from openai import AsyncOpenAI

from .base import LLMError
from .. import settings_store
from ..tools import registry

log = logging.getLogger("llm.openai")

MAX_TOOL_ITERS = 5  # safety bound on the tool-calling loop


def _client() -> AsyncOpenAI:
    key = settings_store.get("openai_api_key")
    if not key:
        raise LLMError("OpenAI API key not set (configure it in the dashboard)")
    base_url = settings_store.get("openai_base_url") or None
    return AsyncOpenAI(api_key=key, base_url=base_url)


class OpenAIProvider:
    async def generate(self, system_prompt, messages, model, temperature,
                       max_tokens, device_id):
        client = _client()
        convo = [{"role": "system", "content": system_prompt}] + messages

        # Only enabled + authorized tools are offered to the model.
        tool_schemas = registry.openai_schemas()

        for _ in range(MAX_TOOL_ITERS):
            kwargs = dict(
                model=model,
                messages=convo,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if tool_schemas:
                kwargs["tools"] = tool_schemas
                kwargs["tool_choice"] = "auto"

            try:
                resp = await client.chat.completions.create(**kwargs)
            except Exception as e:  # noqa: BLE001
                raise LLMError(str(e)) from e

            msg = resp.choices[0].message

            if not getattr(msg, "tool_calls", None):
                return (msg.content or "").strip()

            # Model asked to call tools: run them and feed results back.
            convo.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
            })
            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = await registry.execute(name, args, device_id)
                convo.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                })

        # Ran out of tool iterations — return best-effort text.
        return (msg.content or "").strip() or "…"

    async def test(self, model: str) -> dict:
        client = _client()
        # List models as a lightweight auth check, and confirm the chosen
        # model is available.
        models = [m.id for m in (await client.models.list()).data]
        return {
            "ok": True,
            "model_available": model in models,
            "models": sorted(models),
        }
