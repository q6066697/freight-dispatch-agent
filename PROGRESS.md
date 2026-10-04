# PROGRESS.md

Running log. After each stage: what's done, what's next. Lets work resume if
context is lost — read CLAUDE.md + PLAN.md + this file.

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
