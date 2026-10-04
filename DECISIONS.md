# DECISIONS.md

Architectural / implementation decisions and the reasoning behind them.

## D1 — LangGraph `StateGraph` with a supervisor router
**Decision:** Model the pipeline as a `StateGraph` where a `supervisor` function
decides the next node from the current state (conditional edges), rather than a
fixed linear chain.
**Why:** The task requires supervisor-routing and branching (e.g. incomplete
request → `clarify` and stop; attack → refuse and stop). Conditional edges keyed
off state make the control flow explicit and testable.

## D2 — Pydantic v2 for all structured data
**Decision:** Use Pydantic v2 models for the extracted request, API request/
response, and carrier options.
**Why:** Validation + JSON schema for free, plays well with FastAPI, and lets the
mock provider and real LLMs share the same target schema.

## D3 — SQLite via stdlib `sqlite3`, read-only URI
**Decision:** Open the DB with `sqlite3.connect("file:...?mode=ro", uri=True)` for
the SQL agent. Seed/build uses a normal read-write connection.
**Why:** Read-only at the connection level is defense-in-depth: even if the SQL
guard were bypassed, writes/DDL cannot execute. No external DB engine needed.

## D4 — SQL guard built on `sqlglot`
**Decision:** Parse candidate SQL with `sqlglot` (sqlite dialect). Reject if: not
exactly one statement, not a `SELECT`, references a table outside the whitelist,
or contains forbidden tokens (PRAGMA, ATTACH, comments). Enforce a `LIMIT` by
injecting one if absent. Execute only after it passes.
**Why:** Token/regex-only filtering is brittle; an AST catches comment tricks,
stacked queries, and disguised keywords. Parsing is the project's core safety
story and must be demonstrably robust.

## D5 — Deterministic pricing, no LLM
**Decision:** `app/pricing.py` computes price purely in Python:
`rate_per_km × distance_km` plus multiplicative/additive surcharges (urgency,
body type, partial vs full load).
**Why:** Money must be reproducible, auditable, and testable. LLMs are
non-deterministic and can hallucinate numbers — unacceptable for quotes.

## D6 — Provider abstraction, `mock` is default
**Decision:** One `LLMProvider` interface with `complete(...)` /
`extract_json(...)`; concrete `mock | openai | anthropic | ollama` selected by
`LLM_PROVIDER` env (default `mock`). Mock is deterministic and rule-based.
**Why:** The whole graph, tests, and eval must run offline with no keys. A mock
that mimics the real extraction/response contract makes CI and portfolio review
trivial, while real providers are a config flip away.

## D7 — Langfuse tracing is optional and no-op by default
**Decision:** `app/tracing.py` exposes a tracer that is a no-op unless
`LANGFUSE_ENABLED` + keys are set.
**Why:** Observability is a nice-to-have; it must never be a hard dependency or
break offline runs.

## D9 — Transparent additive pricing model
**Decision:** `price = max(min_price, round100( base × load_factor × (1 + urgency%
+ body% ) ))` where `base = rate_per_km × distance_km`. `rate_per_km` is already
body-type-specific (from `rates`). The extra `body%` (реф +8%, изотерм +4%, тент/
борт 0%) models refrigeration/temperature-handling service cost — not vehicle cost
— so it is not a double count. Urgency (`срочно`/next-day) = +25%. `load_factor`
is 1.0 for a full truck; for `догруз` (partial) it is the max of weight- and
volume-share of the truck, clamped to [0.4, 1.0]. Every component is returned in a
`PriceBreakdown` for auditability.
**Why:** Quotes must be explainable to a client line by line and reproducible in
tests. Keeping it additive + a breakdown object makes both trivial.

## D8 — City-pair distances live in the `routes` table
**Decision:** Distances are looked up from `routes`, not computed from
coordinates. Missing pair → request cannot be priced → responder explains.
**Why:** Keeps pricing deterministic and data-driven; matches how a real
dispatcher works from a rate sheet, and avoids a geo dependency.
