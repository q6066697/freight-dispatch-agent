"""Ollama (local) backend over its HTTP API. Uses httpx; no API key needed."""

from __future__ import annotations

from app.config import get_settings
from app.llm.base import ChatLLMProvider


class OllamaProvider(ChatLLMProvider):
    name = "ollama"

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = settings.resolved_model()

    def _chat(self, system: str, user: str) -> str:
        import httpx  # lazy import

        resp = httpx.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "stream": False,
                "options": {"temperature": 0},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")
