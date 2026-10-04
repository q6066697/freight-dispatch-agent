"""Anthropic (Claude) backend. Imported lazily so mock mode needs no SDK/key."""

from __future__ import annotations

from app.config import get_settings
from app.llm.base import ChatLLMProvider


class AnthropicProvider(ChatLLMProvider):
    name = "anthropic"

    def __init__(self) -> None:
        from anthropic import Anthropic  # lazy import

        settings = get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.resolved_model()

    def _chat(self, system: str, user: str) -> str:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts = [block.text for block in resp.content if getattr(block, "type", "") == "text"]
        return "".join(parts)
