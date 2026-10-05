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

## D18 — LLM-SQL result contract + semantic filter; distance is route-derived
**Decision:** Rows returned by the model's SQL are accepted only if they satisfy a
column/type **contract** (`app/sql_contract.py`: carrier, plate, body_type,
capacity_t, volume_m3, current_city, rating, rate_per_km, min_price, payment_terms,
distance_km — numerics must parse) AND pass a deterministic **semantic filter**
(body_type matches, capacity_t ≥ weight_t, carrier payment_terms compatible).
Otherwise the SQL agent uses the parameterized fallback and records
`fallback_reason ∈ {guard_rejected, zero_rows, missing_columns, invalid_values,
semantic_mismatch}`. Pricing never trusts the model's distance: `distance_km` is
looked up deterministically from `routes` by normalized origin/destination.
**Why:** Real eval (ollama qwen2.5:3b) crashed with `KeyError: 'distance_km'` — the
model's query passed the guard but didn't join `routes`, and separately confused
payment/currency and used `body_type LIKE '%трубы%'`. A guard proves a query is
*safe*; it cannot prove it is *correct*. The contract + semantic filter + route-derived
distance make a wrong-but-safe query fall back deterministically instead of
corrupting pricing. See docs/case-sql-contract.md.

## D19 — Distinct `no_route` status
**Decision:** When origin/destination are known but the pair is absent from `routes`,
the status is `no_route` (its own deterministic reply), separate from `no_options`
(route known, but no suitable truck).
**Why:** The two are different answers to the client ("we don't serve that lane" vs
"no free truck right now") and are worth measuring separately in eval.

## D20 — Eval runner is crash-isolated, append-only, resumable
**Decision:** `run_eval` wraps each case in try/except (a failing case becomes a
record with `status="error"` and the exception type; the run continues), streams one
JSON record per case to `eval/runs/<provider>_<timestamp>.jsonl`, supports
`--resume <file>` (skip ids already present), and aggregates the final table from the
jsonl. Metrics add `error_rate` and the `sql_path` / `fallback_reason` distributions.
**Why:** A real run takes ~15 min/case on CPU; one bad case must not throw away hours
of completed work, and an overnight run must be resumable after an interruption.

## D14 — Grounding: no_options reply is deterministic; LLM reply is guard-checked
**Decision:** The responder never invents data. When there are no options (any
status without options) the reply is a fixed Russian template built in Python. When
options exist, the LLM composes the reply from the options list only, then
`guardrails/output_guard.py` verifies every carrier name and price in the text is
present in `state.options`; on any mismatch we fall back to a deterministic grounded
template and emit an `output_guard_blocked` trace event.
**Why:** A real 7B model (ollama/qwen2.5) invented two carriers and prices on a
`no_options` request (see docs/case-hallucination.md). Mock hid it. Deterministic
templates for the empty case + an output guard for the non-empty case make
hallucinated carriers/prices impossible to reach the client.

## D15 — Deterministic city normalization + fallback SQL after the LLM
**Decision:** After extraction, `app/normalize.py` maps inflected/mis-cased city
names to canonical forms (словарь стемов). The `sql_agent` first tries LLM SQL
(guarded, read-only); if no valid query, or a valid query returns 0 rows for a
complete request, it runs a trusted **parameterized** fallback query
(`app/retrieval.py`). The trace records `sql_path = llm_sql | fallback_sql | none`.
**Why:** On CPU a small model writes shaky SQL and echoes inflected city strings
("минска"/"москву"), yielding false `no_options`. Normalization + a deterministic
fallback make retrieval reliable regardless of model quality, while still exercising
the LLM path when it works.

## D16 — Ollama runtime is env-configurable; larger context by default
**Decision:** `OLLAMA_TIMEOUT` (600s), `OLLAMA_KEEP_ALIVE` (30m) and
`OLLAMA_NUM_CTX` (8192) are read from env. num_ctx defaults to 8192 so the Russian
system prompts do not overflow the model's default 4096 window.
**Why:** CPU inference is slow (~minutes/call); a long timeout and keep-alive avoid
reloading the model, and 8192 context prevents silent prompt truncation that garbles
extraction/SQL.

## D17 — Seed data uses country-correct legal forms and phone codes
**Decision:** Carriers use realistic forms by country (BY: ООО/ОДО/ЧТУП/ИП with
+375 25/29/33/44; RU: ООО/ИП +7; LT: UAB +370; PL: Sp. z o.o. +48), derived from
the carrier's home city. Pinned eval prices are recomputed after the reseed.
**Why:** The author is an ex-logistician; the domain must look credible to a
reviewer. "ТОО" is Kazakh, not Belarusian — it was wrong.

## D12 — Central supervisor node with worker-return loop
**Decision:** Build the graph as `START → supervisor`, where `supervisor` holds all
routing logic (a conditional-edge `route()` that reads state flags) and every worker
node (`input_guard, extractor, clarify, sql_agent, pricing, responder`) routes back
to `supervisor`. The supervisor dispatches the next worker or `END`.
**Why:** This is the canonical LangGraph supervisor pattern and makes control flow a
single inspectable function instead of ad-hoc edges scattered between nodes — easier
to test and to draw in the README Mermaid diagram.

## D13 — `trace` and `sql_attempts` use additive reducers
**Decision:** State keys `trace` and `sql_attempts` are `Annotated[list, add]` so
each node returns only its own entry and LangGraph concatenates. Other keys use the
default replace reducer.
**Why:** Nodes stay simple (no read-modify-write of the whole list) and the step
trace is assembled correctly even though the supervisor loop revisits nodes.

## D10 — Task-level provider interface (not raw text completion)
**Decision:** `LLMProvider` exposes task methods — `classify_attack`,
`extract_request`, `generate_sql`, `compose_reply` — rather than only a generic
`complete()`. Real backends share a `ChatLLMProvider` base that implements these in
terms of one `_chat()` primitive + shared Russian prompts; the `mock` provider
implements them directly with deterministic rules.
**Why:** The hard requirement is that `mock` drives the ENTIRE graph and eval
offline, deterministically. A task-level interface lets the mock produce meaningful
structured output without reverse-engineering a prompt string, while real providers
avoid duplicating prompts.

## D11 — `missing_fields` is computed by the node, not the LLM
**Decision:** The extractor LLM only fills field values; the extractor node
computes `missing_fields` from a fixed set of critical fields (origin, destination,
weight_t, body_type). Clarify branch triggers when any critical field is absent.
**Why:** Deterministic, testable branching that does not depend on the model
remembering to populate a bookkeeping field.

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
