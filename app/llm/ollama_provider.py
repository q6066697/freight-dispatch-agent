"""Ollama (local) backend over its HTTP API. Uses httpx; no API key needed.

Runtime knobs come from env (D16): OLLAMA_TIMEOUT, OLLAMA_KEEP_ALIVE, OLLAMA_NUM_CTX.
CPU inference is slow, so the defaults are a long timeout, a resident model, and an
8192-token context so the Russian system prompts do not overflow the 4096 default.
"""

from __future__ import annotations

from app.config import get_settings
from app.llm.base import ChatLLMProvider


class OllamaProvider(ChatLLMProvider):
    name = "ollama"

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = settings.resolved_model()
        self._timeout = settings.ollama_timeout
        self._keep_alive = settings.ollama_keep_alive
        self._num_ctx = settings.ollama_num_ctx

    def _chat(self, system: str, user: str) -> str:
        import httpx  # lazy import

        resp = httpx.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "stream": False,
                "keep_alive": self._keep_alive,
                "options": {"temperature": 0, "num_ctx": self._num_ctx},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")
