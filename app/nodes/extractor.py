"""extractor node: LLM turns free text into a structured ExtractedRequest."""

from __future__ import annotations

from app.llm.base import LLMProvider
from app.normalize import detect_body_type, normalize_request
from app.schemas import ExtractedRequest
from app.state import DispatchState


def extractor_node(state: DispatchState, provider: LLMProvider) -> dict:
    raw = provider.extract_request(state["text"])
    normalized = normalize_request(raw)
    # Deterministic backfill (D21): weak models miss slang like «еврофура»/«фура».
    if not normalized.get("body_type"):
        inferred = detect_body_type(state["text"])
        if inferred:
            normalized["body_type"] = inferred
    request = ExtractedRequest.from_raw(normalized)
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
