"""clarify node: when critical fields are missing, ask the client one question."""

from __future__ import annotations

from app.llm.base import LLMProvider
from app.state import DispatchState

_FIELD_QUESTIONS = {
    "origin": "из какого города забрать груз",
    "destination": "в какой город доставить",
    "weight_t": "какой вес груза (в тоннах)",
    "body_type": "какой нужен тип кузова (тент, реф, изотерм или борт)",
}


def build_clarify_question(missing: list[str]) -> str:
    parts = [_FIELD_QUESTIONS[f] for f in missing if f in _FIELD_QUESTIONS]
    if not parts:
        return "Уточните, пожалуйста, детали заявки, и я подберу машину."
    if len(parts) == 1:
        body = parts[0]
    else:
        body = ", ".join(parts[:-1]) + " и " + parts[-1]
    return f"Чтобы подобрать машину и рассчитать цену, подскажите, пожалуйста: {body}?"


def clarify_node(state: DispatchState, provider: LLMProvider) -> dict:
    missing = state.get("missing_fields", [])
    question = build_clarify_question(missing)
    step = {"step": "clarify", "status": "ok", "detail": {"missing": missing}}
    return {
        "clarify_question": question,
        "reply": question,
        "status": "clarify",
        "trace": [step],
    }
