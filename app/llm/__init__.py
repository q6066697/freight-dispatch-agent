"""LLM provider abstraction. Import `get_provider` to obtain the active backend."""

from app.llm.base import LLMProvider, get_provider

__all__ = ["LLMProvider", "get_provider"]
