"""LangGraph state definition for the dispatcher graph.

`trace` and `sql_attempts` accumulate across the supervisor loop via an additive
reducer (DECISIONS.md D13); every other key uses the default replace reducer.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class DispatchState(TypedDict, total=False):
    # input
    text: str
    provider_name: str | None

    # input_guard
    screen: dict[str, Any] | None
    blocked: bool
    block_category: str | None

    # extractor
    extracted: dict[str, Any] | None
    request: dict[str, Any] | None  # ExtractedRequest.model_dump()
    missing_fields: list[str]
    needs_clarify: bool

    # sql_agent
    sql: str | None
    sql_done: bool
    sql_attempts: Annotated[list[dict[str, Any]], operator.add]
    rows: list[dict[str, Any]]

    # pricing
    priced: bool
    options: list[dict[str, Any]]

    # output
    reply: str | None
    status: str
    clarify_question: str | None

    # observability
    trace: Annotated[list[dict[str, Any]], operator.add]
