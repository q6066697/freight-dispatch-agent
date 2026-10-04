"""responder node: LLM composes the final Russian reply with up to 3 options."""

from __future__ import annotations

from app.llm.base import LLMProvider
from app.state import DispatchState


def responder_node(state: DispatchState, provider: LLMProvider) -> dict:
    request = state.get("request") or {}
    options = state.get("options") or []
    top = options[:3]

    reply = provider.compose_reply(request, top)
    status = "ok" if top else "no_options"

    step = {
        "step": "responder",
        "status": status,
        "detail": {"offered": len(top)},
    }
    return {"reply": reply, "status": status, "trace": [step]}
