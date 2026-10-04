"""OpenAI backend. Imported lazily so mock mode never needs the SDK/key."""

from __future__ import annotations

from app.config import get_settings
from app.llm.base import ChatLLMProvider


class OpenAIProvider(ChatLLMProvider):
    name = "openai"

    def __init__(self) -> None:
        from openai import OpenAI  # lazy import

        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self._client = OpenAI(
            api_key=settings.openai_api_key, base_url=settings.openai_base_url
        )
        self._model = settings.resolved_model()

    def _chat(self, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""
