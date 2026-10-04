"""responder node: compose the final Russian reply, grounded in state (D14).

- No options  → deterministic template, no LLM (can't invent anything).
- Options     → LLM composes from the options list, then the output guard checks
                that every carrier/price is backed by state.options; on a violation
                we fall back to a deterministic grounded template and record an
                `output_guard_blocked` trace event.
"""

from __future__ import annotations

from app.guardrails.output_guard import check_reply
from app.llm.base import LLMProvider
from app.reply_templates import grounded_reply, no_options_reply
from app.state import DispatchState


def responder_node(state: DispatchState, provider: LLMProvider) -> dict:
    request = state.get("request") or {}
    options = state.get("options") or []
    top = options[:3]

    if not top:
        step = {"step": "responder", "status": "no_options",
                "detail": {"offered": 0, "mode": "deterministic"}}
        return {"reply": no_options_reply(request), "status": "no_options",
                "trace": [step]}

    llm_reply = provider.compose_reply(request, top)
    screen = check_reply(llm_reply, top)

    trace: list[dict] = []
    if screen.ok:
        reply, mode = llm_reply, "llm"
    else:
        reply, mode = grounded_reply(request, top), "grounded_fallback"
        trace.append({
            "step": "output_guard_blocked",
            "status": "blocked",
            "detail": {"violations": screen.violations},
        })

    trace.append({"step": "responder", "status": "ok",
                  "detail": {"offered": len(top), "mode": mode}})
    return {"reply": reply, "status": "ok", "trace": trace}
