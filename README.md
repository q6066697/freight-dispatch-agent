# Freight Dispatch Agent

A multi-agent **freight dispatcher** built on [LangGraph](https://github.com/langchain-ai/langgraph).
You send a cargo request in plain Russian — *"Нужно отвезти 12 тонн труб из Минска в
Москву в четверг, тент, оплата безнал"* — and the system extracts the structured
order, finds matching trucks in a database, prices each option deterministically, and
replies with 1–3 concrete offers (carrier, truck, price, ETA).

It runs **fully offline by default** (a deterministic `mock` LLM), so you can clone,
test, and evaluate it with no API keys and no internet.

> **Why this project.** The author spent 12 years as a sole proprietor in freight
> logistics (Belarus / Russia). Dispatchers read messy free-text requests all day,
> mentally match them to available trucks, and quote a price from a rate sheet. This
> project encodes that workflow — with the parts that must be *safe* and *exact*
> (database access, pricing) kept out of the LLM's hands.

> **Data is synthetic.** The carriers, trucks, routes, and tariffs in `db/seed.py`
> are plausible but invented. No real company or rate sheet is used.

---

## Architecture

A central **supervisor** routes between worker nodes until a reply is ready. Input is
screened for attacks *before* anything else; incomplete requests short-circuit to a
clarifying question; pricing is deterministic Python, never the LLM.

```mermaid
flowchart TD
    START([client request]) --> SUP{supervisor}
    SUP -->|first| IG[input_guard<br/>prompt-injection / off-topic]
    IG --> SUP
    SUP -->|clean| EX[extractor<br/>text → structured order]
    EX --> SUP
    SUP -->|missing critical field| CL[clarify<br/>ask one question] --> SUP
    SUP -->|complete| SQL[sql_agent<br/>guarded text-to-SQL]
    SQL --> SUP
    SUP --> PR[pricing<br/>deterministic quote]
    PR --> SUP
    SUP --> RE[responder<br/>compose RU reply]
    RE --> SUP
    SUP -->|attack / clarify / done| END([reply + step trace])
```

| Node | Job | LLM? |
|---|---|---|
| `input_guard` | Detect prompt injection, data-tamper, system-prompt leaks, off-topic. Rules **+** an LLM classifier; refuse politely on a hit. | rules + LLM |
| `extractor` | Turn free text into an `ExtractedRequest` (origin, destination, cargo, weight, volume, body type, date, payment, urgency, load type). | yes |
| `clarify` | If a critical field (origin / destination / weight / body type) is missing, ask one targeted question and stop. | no |
| `sql_agent` | Generate a `SELECT`, pass it through the SQL guard, run it read-only. Up to 2 self-corrections on rejection. | yes (SQL only) |
| `pricing` | Compute each option's price from the rate sheet. | **no — pure Python** |
| `responder` | Compose the final Russian reply with up to 3 options. | yes |

### Why pricing is deterministic

Quotes are money. They must be reproducible, auditable, and testable — an LLM is none
of those. `app/pricing.py` computes:

```
base       = rate_per_km × distance_km
after_load = base × load_factor          # догруз (partial load) is cheaper than a full truck
total      = after_load × (1 + urgency% + body%)
total      = max(total, min_price), rounded to the nearest 100 RUB
```

Every quote returns a full `PriceBreakdown`, so the client-facing number can be
explained line by line and pinned in unit tests. Urgency is +25%; a reefer adds +8%
and an isotherm +4% for temperature handling (on top of the body-specific per-km
tariff); a догруз is billed by its weight/volume share of the truck, floored at 40%.

### How the guardrails work

**SQL guard** (`app/guardrails/sql_guard.py`) — the core safety story. Generated SQL
is parsed into an AST with [`sqlglot`](https://github.com/tobymao/sqlglot) and accepted
only if **all** of these hold:

- exactly **one** statement (no stacked `;` queries);
- it is a `SELECT` (or a `UNION` of selects) — never INSERT/UPDATE/DELETE/DDL;
- every referenced table is in the whitelist (`carriers, trucks, routes, rates`);
- no SQL comments (`--`, `/* */`), no `PRAGMA` / `ATTACH` / `VACUUM`, no dangerous
  functions (`load_extension`, `readfile`, …);
- a `LIMIT` is injected if absent and clamped if too large.

As defense-in-depth, the query then runs on a connection opened **read-only**
(`sqlite3` URI `?mode=ro`), so even a query that somehow slipped past the parser
cannot write or run DDL.

**Input guard** (`app/guardrails/input_guard.py`) — rule patterns (Russian + English)
for prompt injection, data-tamper phrasing, and system-prompt-leak attempts, combined
with the provider's LLM classifier. Any hit → a polite refusal, before extraction.

---

## Eval

The eval harness (`eval/run_eval.py`) runs **42 labeled cases**
(`eval/dataset.jsonl`) — normal orders, dispatcher slang (*еврофура, тентовка,
догруз*), incomplete requests that must trigger a clarification, 12 attacks, off-topic
messages, and an edge case — through the full graph and reports:

| Metric | Value (mock) |
|---|---|
| Status accuracy | 100.0% |
| Extraction accuracy (overall) | 100.0% |
| Clarify precision | 100.0% |
| Clarify recall | 100.0% |
| SQL validity rate | 100.0% |
| SQL guard-block rate | 0.0% |
| **Attack block rate (n=12)** | **100.0%** |
| Off-topic block rate | 100.0% |
| Price correctness vs. reference (n=3) | 100.0% |
| Latency p50 / p95 | 9.1 ms / 43.9 ms |

Per-field extraction accuracy (origin, destination, weight, body type, payment,
urgency, load type) is 100% on this dataset. The full table is written to
`eval/results.md` on every run.

> **Reading the numbers.** In `mock` mode the extractor is a deterministic rule-based
> NLU and the SQL builder always emits a valid query, so extraction and SQL-validity
> are 100% and the SQL-guard *block* rate is 0% — attacks are stopped earlier, at
> `input_guard`. The guard's blocking behavior is exercised directly by ~20 attack
> vectors in `tests/test_sql_guard.py`. On a real model these rates become a genuine
> measure of model quality; the harness is identical.

Run it:

```bash
python -m eval.run_eval
```

---

## Quick start

### 1. Mock mode — no keys, no internet (default)

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows
# source .venv/bin/activate       # macOS/Linux
pip install -e ".[dev]"

python -m db.seed                 # build data/freight.db (synthetic)
python -m app.cli "Нужно отвезти 12 тонн труб из Минска в Москву в четверг, тент, безнал"

pytest -q && ruff check .         # tests green, lint clean
python -m eval.run_eval           # eval table + eval/results.md
```

Run the HTTP API:

```bash
uvicorn app.api:app --reload
# POST /dispatch  {"text": "..."}      GET /health
curl -s localhost:8000/health
curl -s -X POST localhost:8000/dispatch -H "content-type: application/json" \
     -d '{"text":"Реф 10 тонн из Минска в Санкт-Петербург, безнал"}'
```

### 2. Real model

Copy `.env.example` → `.env` and set a provider + key (nothing else changes):

```env
LLM_PROVIDER=anthropic           # or openai | ollama
ANTHROPIC_API_KEY=sk-ant-...
# LLM_MODEL=claude-sonnet-4-6    # optional override
```

Install the matching extra and run as above:

```bash
pip install -e ".[anthropic]"    # or ".[openai]"; ollama needs no extra
python -m app.cli --provider anthropic "Еврофура из Бреста в Варшаву, 20 тонн, безнал"
```

Keys are read only from the environment; `.env` is git-ignored and never committed.
Optional Langfuse tracing turns on with `LANGFUSE_ENABLED=true` (+ keys); otherwise
it is a no-op.

### 3. Docker

```bash
docker compose up --build
# API on http://localhost:8000  (mock by default; pass LLM_PROVIDER / keys to use a real model)
```

---

## Project layout

```
app/
  config.py          env-driven settings
  graph.py           supervisor StateGraph + dispatch()
  state.py           LangGraph state
  schemas.py         Pydantic models (request, options, API)
  pricing.py         deterministic pricing
  db.py              read-only SQLite connection + table whitelist
  api.py  cli.py     FastAPI + command line
  nodes/             input_guard, extractor, clarify, sql_agent, pricing_node, responder
  llm/               provider abstraction: mock (default), openai, anthropic, ollama
  guardrails/        sql_guard.py, input_guard.py
db/                  schema.sql + seed.py (synthetic data)
eval/                dataset.jsonl, run_eval.py, results.md
tests/               pytest suite (guardrails, pricing, graph, API, eval)
```

---

## Limitations & next steps

- The `mock` extractor is rule-based: great for offline CI and demos, but real slang
  coverage is the real model's job. The eval harness is the tool to measure that.
- Distances come from a `routes` table of known city pairs; an unknown pair yields no
  price. A real system would fall back to a routing/geo service.
- Truck location vs. pickup city isn't used as a hard filter (any free truck can serve
  a route). A production version would price empty-run (подача) to the origin.
- No persistence of conversations / multi-turn clarify loop yet — clarify ends the
  graph with a question; the client's follow-up is a new request.
- Guardrails are strong but not a substitute for least-privilege DB credentials in
  production; the read-only connection is the backstop that matters.

---

## Author

Built by **q6066697** — 12 years as a freight sole-proprietor, now an AI/LLM engineer.
GitHub: https://github.com/q6066697

---

## Кратко по-русски

Мультиагентный диспетчер грузоперевозок на LangGraph. На входе — заявка свободным
текстом по-русски, на выходе — 1–3 варианта (перевозчик, машина, цена, срок).

- **Граф с супервайзером:** `input_guard` (защита от инъекций и оффтопа) → `extractor`
  (текст → структура) → `clarify` (если не хватает критичных полей — уточняющий
  вопрос) → `sql_agent` (text-to-SQL с жёсткими guardrails) → `pricing`
  (детерминированный расчёт на Python, **без LLM**) → `responder` (ответ клиенту).
- **Безопасность SQL:** запрос разбирается через `sqlglot`, разрешён только один
  `SELECT` по таблицам из белого списка, запрещены комментарии / `PRAGMA` / `ATTACH` /
  изменения данных, принудительный `LIMIT`, соединение открыто **только на чтение**
  (`mode=ro`).
- **Почему цена считается без LLM:** деньги должны быть воспроизводимыми и проверяемыми
  тестами. Формула прозрачна: тариф × расстояние × коэффициент загрузки × (1 +
  срочность% + надбавка за кузов), не ниже минималки.
- **Запуск без ключей:** провайдер `mock` детерминированный, весь граф, тесты и eval
  работают офлайн. Данные в базе — синтетические.
- **Как прогнать:** `python -m db.seed`, затем `pytest`, `ruff check .`,
  `python -m eval.run_eval`, или `uvicorn app.api:app`. Реальная модель включается
  одной переменной `LLM_PROVIDER` в `.env`.
```
python -m app.cli "Нужно отвезти 12 тонн труб из Минска в Москву в четверг, тент, безнал"
```
