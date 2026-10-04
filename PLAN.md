# PLAN.md — Build stages

Checkbox per stage. After each: run `pytest` + `ruff check .`, update
`PROGRESS.md`, then `git commit` (English message). No `git push`.

- [ ] **S0. Skeleton + deps.** Repo init, `.gitignore`, `.env.example`,
  `pyproject.toml` (deps + ruff + pytest config), package dirs with `__init__.py`,
  `app/config.py` (env settings). venv created, deps installed.
- [ ] **S1. DB + seed.** `db/schema.sql` (carriers, trucks, routes, rates),
  `db/seed.py` generating synthetic data (~15 carriers, ~40 trucks, ~30 routes,
  rates). `app/db.py` read-only connection helper. Sanity script.
- [ ] **S2. Guardrails + tests.** `app/guardrails/sql_guard.py` (sqlglot parse,
  single SELECT, whitelist, forced LIMIT, block PRAGMA/ATTACH/comments/multi-stmt,
  read-only exec). `app/guardrails/input_guard.py` (rule-based injection/offtopic
  detection + hook for LLM classifier). `tests/test_sql_guard.py` with many attack
  vectors.
- [ ] **S3. Pricing + tests.** `app/pricing.py` deterministic:
  base = rate_per_km × distance_km, + surcharges (urgency, body type, full vs
  partial load). `tests/test_pricing.py`.
- [ ] **S4. LLM providers.** `app/llm/base.py` interface, `mock.py` (deterministic,
  default), `openai_provider.py`, `anthropic_provider.py`, `ollama_provider.py`,
  factory in `app/llm/__init__.py`. `app/tracing.py` Langfuse no-op wrapper.
- [ ] **S5. Graph (mock).** Pydantic extraction schema + API schemas
  (`app/schemas.py`), graph state (`app/state.py`), nodes
  (`input_guard, extractor, clarify, sql_agent, pricing_node, responder`),
  supervisor routing, `app/graph.py` StateGraph. Integration test in mock mode.
- [ ] **S6. Eval harness.** `eval/dataset.jsonl` (≥40 cases incl. 10+ attacks,
  incomplete→clarify, slang/typos). `eval/run_eval.py` computes extraction field
  accuracy, clarify P/R, SQL validity + guard-block rate, attack block rate,
  price correctness, latency p50/p95; prints table + writes `eval/results.md`.
- [ ] **S7. API + Docker + CLI.** FastAPI `POST /dispatch`, `GET /health`;
  `app/cli.py`; `Dockerfile` (slim, non-root) + `docker-compose.yml`.
  `tests/test_api.py` via TestClient.
- [ ] **S8. README.** English (+ short Russian section), Mermaid graph diagram,
  why deterministic pricing, guardrails design, eval metrics table from
  results.md, quick start (mock / real / Docker), limitations, Author block
  (https://github.com/q6066697).
- [ ] **S9. Final.** Full `pytest` + eval run, update `PROGRESS.md`, print summary.
