# CLAUDE.md — Project Rules for freight-dispatch-agent

## What this is
A portfolio-grade multi-agent **freight dispatcher** built on **LangGraph**.
Input: a free-text cargo request in Russian. Output: a polite Russian reply with
1–3 carrier/truck/price options, plus a step trace. Domain is real (author ran a
freight sole-proprietorship in Belarus/Russia for 12 years).

## Hard rules
1. **Autonomous mode.** Make decisions yourself, record each non-trivial one in
   `DECISIONS.md` (decision + why). Keep working until the whole plan is done and
   `pytest` + `ruff` are green.
2. **No secrets in files.** API keys come only from environment variables.
   `.env` is git-ignored; only `.env.example` is committed with placeholders.
3. **Default to zero-dependency runtime.** `LLM_PROVIDER=mock` is the default and
   must let the ENTIRE graph, all tests, and the full eval run without any API key
   or internet access. Mock output must be deterministic.
4. **Pricing is deterministic Python.** Never ask an LLM to compute a price.
5. **SQL is guarded.** Every query the SQL agent runs passes through
   `app/guardrails/sql_guard.py`: single `SELECT` only, table whitelist, forced
   `LIMIT`, no PRAGMA/ATTACH/comment tricks, parsed with `sqlglot`. DB connection
   is opened read-only (`file:...?mode=ro`).
6. **Attacks must be blocked.** Prompt-injection / data-mutation / system-prompt
   leak attempts are refused politely. Eval target = 100% attack block rate.
7. **venv only.** Never install globally. Use `.venv`.
8. **Commit after each stage** with a clear English message. Never `git push`.

## Tech choices
- Python 3.11, Pydantic v2, LangGraph, FastAPI, SQLite (stdlib `sqlite3`),
  `sqlglot` for SQL parsing, `pytest`, `ruff`.
- LLM providers: `openai | anthropic | ollama | mock` behind one interface.
- Optional Langfuse tracing, env-gated, no-op when disabled.

## Layout
```
app/        graph, nodes, llm providers, guardrails, pricing, api, cli, config
db/         schema.sql + seed.py (synthetic data)
eval/       dataset.jsonl, run_eval.py, results.md
tests/      pytest suite
```

## How to run (mock, no keys)
```
python -m db.seed            # build data/freight.db
python -m app.cli "Нужно отвезти 12 тонн труб из Минска в Москву в четверг, тент"
uvicorn app.api:app          # HTTP API
python -m eval.run_eval      # eval harness
pytest -q && ruff check .
```

## Conventions
- All user-facing text to the client is in Russian; code/comments/commits English.
- Keep nodes pure-ish: read graph state, return a partial state update.
- Data is SYNTHETIC — say so in README.
