# PROGRESS.md

Running log. After each stage: what's done, what's next. Lets work resume if
context is lost — read CLAUDE.md + PLAN.md + this file.

## Status: S7 done (2026-10-04)

### Done (S7)
- app/api.py: FastAPI POST /dispatch, GET /health; lifespan seeds DB if missing.
- app/cli.py: python -m app.cli "<text>" [--provider] [--json].
- Dockerfile (python:3.11-slim, non-root uid 10001, seeds DB at build, healthcheck),
  docker-compose.yml, .dockerignore.
- tests/test_api.py (5) via TestClient. Full suite: 90 passing, ruff clean.
- Docker verified available (29.1.2); image build verified in S8 after README.

### Next (S8)
- README (EN + short RU), Mermaid diagram, metrics table, quick start, author.

---

## Status: S6 done (2026-10-04)

### Done (S6)
- eval/dataset.jsonl: 42 labeled cases (18 normal/slang, 8 incomplete→clarify,
  12 attacks, 3 offtopic, 1 edge/no_options); 3 cases pinned with reference price.
- eval/run_eval.py: computes extraction field accuracy, clarify P/R, SQL validity
  + guard-block, attack/offtopic block rate, price correctness, latency p50/p95;
  prints table + writes eval/results.md.
- tests/test_eval.py regression thresholds.
- Mock-mode results: status 100%, extraction 100%, clarify P/R 100%, attack block
  100%, offtopic 100%, price 100%, SQL validity 100%. 85 tests passing.

### Next (S7)
- FastAPI (POST /dispatch, GET /health), CLI, Dockerfile + compose, API test.

---

## Status: S5 done (2026-10-04)

### Done (S5)
- app/schemas.py: ExtractedRequest (from_raw computes missing_fields), CarrierOption,
  API models (DispatchRequest/Response, StepTrace, HealthResponse).
- app/state.py: DispatchState TypedDict; trace & sql_attempts additive reducers.
- app/nodes/: input_guard (rule+LLM, polite refusals), extractor, clarify,
  sql_agent (guard + up to 2 self-heal retries, read-only exec), pricing_node
  (dedupe per carrier, sort by price), responder.
- app/graph.py: supervisor + route() conditional edges, build_graph/get_graph/
  dispatch/to_response.
- tests/conftest.py (auto-seed DB), tests/test_graph.py (9). Full suite: 84 passing.

### Next (S6)
- eval/dataset.jsonl (≥40, 10+ attacks) + eval/run_eval.py + results.md.

---

## Status: S4 done (2026-10-04)

### Done (S4)
- app/llm/base.py: task-level LLMProvider ABC (classify_attack, extract_request,
  generate_sql, compose_reply) + ChatLLMProvider (shared RU prompts, _chat) +
  get_provider() factory. CRITICAL_FIELDS defined here.
- app/llm/mock.py: deterministic rule-based RU extractor (inflected cities, slang
  еврофура/тентовка/догруз, weight/volume/body/payment/urgency/date/cargo),
  SQL template, template reply, attack classifier via input_guard rules.
- app/llm/{openai,anthropic,ollama}_provider.py: lazy-imported real backends.
- app/tracing.py: Langfuse no-op unless enabled.
- tests/test_providers.py (11). Full suite: 75 passing.

### Next (S5)
- Pydantic schemas, graph state, nodes, StateGraph (mock), integration test.

---

## Status: S3 done (2026-10-04)

### Done (S3)
- app/pricing.py: deterministic price_quote() + load_factor(); base = rate/km ×
  distance, × load_factor (догруз), × (1 + urgency% + body%), min_price floor,
  round to 100. Returns itemized PriceBreakdown. See DECISIONS D9.
- tests/test_pricing.py: 12 passing.

### Next (S4)
- LLM providers (base/mock/openai/anthropic/ollama) + tracing no-op.

---

## Status: S2 done (2026-10-04)

### Done (S2)
- app/guardrails/sql_guard.py: sqlglot AST validation — single SELECT/UNION only,
  table whitelist, forbidden keywords/nodes/functions, no comments/stacking,
  LIMIT inject+clamp. validate_sql() + guard_sql().
- app/guardrails/input_guard.py: rule-based screen_input() for prompt_injection /
  system_leak / sql_tamper / offtopic (RU+EN).
- tests: 52 passing (test_sql_guard.py incl. ~20 attacks, test_input_guard.py).

### Next (S3)
- app/pricing.py deterministic pricing + tests/test_pricing.py.

---

## Status: S1 done (2026-10-04)

### Done
- **S0** skeleton: control docs, pyproject (deps+ruff+pytest), package dirs,
  app/config.py, venv + deps installed, git init, commit.
- **S1** DB: db/schema.sql (carriers, trucks, routes, rates), db/seed.py
  (deterministic synthetic data — carriers=15, trucks=40, routes=44, rates=25),
  app/db.py read-only URI connection (write/DDL blocked, verified).

### Next
- **S2** guardrails: app/guardrails/sql_guard.py (sqlglot) + input_guard.py +
  tests/test_sql_guard.py with attack vectors.
