"""LangGraph assembly: a supervisor dispatches workers until a reply is ready.

Flow (DECISIONS.md D12):

    START → supervisor ──▶ input_guard ──▶ supervisor
                        ├▶ extractor    ──▶ supervisor
                        ├▶ clarify      ──▶ supervisor
                        ├▶ sql_agent    ──▶ supervisor
                        ├▶ pricing      ──▶ supervisor
                        ├▶ responder    ──▶ supervisor
                        └▶ END

The `route` function is the whole control policy, keyed off state flags.
"""

from __future__ import annotations

from functools import partial

from langgraph.graph import END, START, StateGraph

from app.config import get_settings
from app.llm import get_provider
from app.llm.base import LLMProvider
from app.nodes.clarify import clarify_node
from app.nodes.extractor import extractor_node
from app.nodes.input_guard import input_guard_node
from app.nodes.pricing_node import pricing_node
from app.nodes.responder import responder_node
from app.nodes.sql_agent import sql_agent_node
from app.schemas import (
    CarrierOption,
    DispatchResponse,
    ExtractedRequest,
    StepTrace,
)
from app.state import DispatchState

WORKERS = ("input_guard", "extractor", "clarify", "sql_agent", "pricing", "responder")


def _supervisor(state: DispatchState) -> dict:
    """No-op node; all routing lives in `route` (conditional edges)."""
    return {}


def route(state: DispatchState) -> str:
    """Decide the next worker (or END) from the current state."""
    if state.get("screen") is None:
        return "input_guard"
    if state.get("reply"):  # refusal / clarify / final reply all land here
        return END
    if state.get("blocked"):
        return END
    if state.get("extracted") is None:
        return "extractor"
    if state.get("needs_clarify"):
        return "clarify"
    if not state.get("sql_done"):
        return "sql_agent"
    if not state.get("priced"):
        return "pricing"
    return "responder"


def build_graph(provider: LLMProvider | None = None):
    """Compile the dispatcher graph bound to a concrete LLM provider."""
    provider = provider or get_provider()

    nodes = {
        "input_guard": input_guard_node,
        "extractor": extractor_node,
        "clarify": clarify_node,
        "sql_agent": sql_agent_node,
        "pricing": pricing_node,
        "responder": responder_node,
    }

    builder = StateGraph(DispatchState)
    builder.add_node("supervisor", _supervisor)
    for name, fn in nodes.items():
        builder.add_node(name, partial(fn, provider=provider))

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        route,
        {**{w: w for w in WORKERS}, END: END},
    )
    for worker in WORKERS:
        builder.add_edge(worker, "supervisor")

    return builder.compile()


_GRAPH_CACHE: dict[str, object] = {}


def get_graph(provider_name: str | None = None):
    key = (provider_name or get_settings().llm_provider or "mock").lower()
    if key not in _GRAPH_CACHE:
        _GRAPH_CACHE[key] = build_graph(get_provider(provider_name))
    return _GRAPH_CACHE[key]


def to_response(state: dict) -> DispatchResponse:
    req = state.get("request")
    options = [CarrierOption(**o) for o in state.get("options", []) or []]
    trace = [StepTrace(**t) for t in state.get("trace", []) or []]
    status = state.get("status") or ("ok" if options else "no_options")
    return DispatchResponse(
        status=status,
        reply=state.get("reply") or "",
        request=ExtractedRequest(**req) if req else None,
        clarify_question=state.get("clarify_question"),
        options=options,
        trace=trace,
    )


def run_graph(text: str, provider_name: str | None = None) -> dict:
    """Run one request end-to-end and return the raw final graph state."""
    return get_graph(provider_name).invoke({"text": text})


def dispatch(text: str, provider_name: str | None = None) -> DispatchResponse:
    """Run one request end-to-end and return the API-shaped response."""
    return to_response(run_graph(text, provider_name))
