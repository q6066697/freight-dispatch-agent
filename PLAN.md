# PLAN.md — Build stages

All stages complete. After each: `pytest` + `ruff check .`, update `PROGRESS.md`,
`git commit` (English). No `git push`.

- [x] **S0. Skeleton + deps.** Repo init, `.gitignore`, `.env.example`,
  `pyproject.toml`, package dirs, `app/config.py`, venv + deps.
- [x] **S1. DB + seed.** `db/schema.sql`, `db/seed.py` (synthetic), `app/db.py`
  read-only connection.
- [x] **S2. Guardrails + tests.** `sql_guard.py` (sqlglot), `input_guard.py`,
  `tests/test_sql_guard.py` + `test_input_guard.py`.
- [x] **S3. Pricing + tests.** `app/pricing.py` deterministic, `test_pricing.py`.
- [x] **S4. LLM providers.** `base.py` + `mock.py` (default) + openai/anthropic/
  ollama, `tracing.py` no-op.
- [x] **S5. Graph (mock).** schemas, state, 6 nodes, supervisor `StateGraph`,
  `test_graph.py`.
- [x] **S6. Eval harness.** `dataset.jsonl` (42 cases, 12 attacks),
  `run_eval.py`, `results.md`, `test_eval.py`.
- [x] **S7. API + Docker + CLI.** FastAPI, CLI, Dockerfile + compose,
  `test_api.py`.
- [x] **S8. README.** EN + RU, Mermaid diagram, metrics, quick start, author.
- [x] **S9. Final.** Clean rebuild, 90 tests green, eval all-green, summary.
