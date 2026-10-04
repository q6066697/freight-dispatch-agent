# PROGRESS.md

Running log. After each stage: what's done, what's next. Lets work resume if
context is lost — read CLAUDE.md + PLAN.md + this file.

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
