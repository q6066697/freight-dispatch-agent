"""extractor node: LLM turns free text into a structured ExtractedRequest."""

from __future__ import annotations

from app.llm.base import LLMProvider
from app.schemas import ExtractedRequest
from app.state import DispatchState


def extractor_node(state: DispatchState, provider: LLMProvider) -> dict:
    raw = provider.extract_request(state["text"])
    request = ExtractedRequest.from_raw(raw)
    needs_clarify = not request.is_complete

    step = {
        "step": "extractor",
        "status": "ok",
        "detail": request.model_dump(),
    }
    return {
        "extracted": raw,
        "request": request.model_dump(),
        "missing_fields": request.missing_fields,
        "needs_clarify": needs_clarify,
        "trace": [step],
    }
