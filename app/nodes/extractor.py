"""extractor node: LLM turns free text into a structured ExtractedRequest.

Robust to malformed model output (D22): if the raw response fails validation we make
one repair call (feeding the error back to the model), then fall back to deterministic
type coercion, and finally to an empty request — so a bad extraction degrades to a
clarifying question, never a crash.
"""

from __future__ import annotations

from pydantic import ValidationError

from app.llm.base import LLMProvider
from app.normalize import coerce_types, detect_body_type, normalize_request
from app.schemas import ExtractedRequest
from app.state import DispatchState


def _with_body_backfill(data: dict, text: str) -> dict:
    # Deterministic slang backfill (D21): weak models miss «еврофура»/«фура».
    if not data.get("body_type"):
        inferred = detect_body_type(text)
        if inferred:
            data = {**data, "body_type": inferred}
    return data


def _safe_extract(provider: LLMProvider, text: str, error: str) -> dict:
    """Repair call; tolerant of providers whose extract_request lacks `error`."""
    try:
        return provider.extract_request(text, error=error)
    except TypeError:
        return provider.extract_request(text)


def extractor_node(state: DispatchState, provider: LLMProvider) -> dict:
    text = state["text"]
    raw = provider.extract_request(text)
    status = "ok"

    try:
        request = ExtractedRequest.from_raw(_with_body_backfill(normalize_request(raw), text))
    except ValidationError as e:
        status = "repaired"
        raw2 = _safe_extract(provider, text, str(e))
        try:
            request = ExtractedRequest.from_raw(
                _with_body_backfill(normalize_request(raw2), text)
            )
        except ValidationError:
            try:  # deterministic coercion — cannot raise under normal inputs
                request = ExtractedRequest.from_raw(_with_body_backfill(coerce_types(raw2), text))
            except Exception:  # noqa: BLE001 - absolute guarantee: never drop a request
                request = ExtractedRequest.from_raw({})

    needs_clarify = not request.is_complete
    step = {"step": "extractor", "status": status, "detail": request.model_dump()}
    return {
        "extracted": raw,
        "request": request.model_dump(),
        "missing_fields": request.missing_fields,
        "needs_clarify": needs_clarify,
        "trace": [step],
    }
