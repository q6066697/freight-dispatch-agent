# PROGRESS.md

Running log. After each stage: what's done, what's next. Lets work resume if
context is lost — read CLAUDE.md + PLAN.md + this file.

## Status: S12 "Real-model results & release prep" done (2026-10-05)

### Real eval analysed (ollama qwen2.5:3b, CPU, n=12 subset)
Results: status 83.3%, errors 0%, extraction 96.8% (body_type 83%), clarify P/R
60/100%, SQL path llm/fallback 0/3, attack 100%, hallucination 0%, price 66.7%,
p50 ~166s / p95 ~1084s. Both status misses (normal_02 «еврофура», normal_07 «фура»)
= one model error: body_type left null on slang → false clarify (normal_07 price miss
is downstream). No labeling errors, no pipeline bugs. LLM-SQL 0/3 usable → fallback
carried every priced case → 0% hallucination, 0% crashes (S10/S11 fixes held).
Full write-up: docs/real-model-error-analysis.md.

### Changes
- D21 deterministic body-type backfill from raw text (slang lexicon) in extractor
  when the model leaves body_type empty. General, not overfit; mock eval unchanged
  (100%); NOT yet re-validated on the real model.
- README "Mock vs real model" filled with the qwen2.5:3b column (conditions noted:
  CPU-only, n=12, indicative) + domain Future work (подача/empty-run, load date &
  availability, cargo dimensions/длинномер, догруз/groupage, stronger model/GPU).

### Verification
- pytest 131 passed, ruff clean. eval(mock,46) still all-green (hallucination 0%).

### Publication safety checks (all pass)
- `git log --all -- .env` empty → .env never tracked. Tracked .env* = only
  .env.example. `.env` currently git-ignored.
- No real key tokens (sk-/sk-ant-) anywhere in history. Broader api_key/secret/token
  scan: only env-backed reads + README placeholder `sk-ant-...`; .env.example values
  empty.
- .gitignore covers .env, .venv/, data/*.db, eval/runs/.
- Repo ready to publish; push deferred to the user (manual GitHub repo + first push).

---

## Status: S11 "Real-model eval robustness" done (2026-10-05)

### The second bug (found by real eval, ollama qwen2.5:3b)
`run_eval --provider ollama` crashed on the 3rd case with
`KeyError: 'distance_km'` in pricing: the model's SQL passed sql_guard and returned
rows, but it never joined `routes` (and elsewhere confused payment/currency, filtered
body_type by the cargo word). A safe query that is still wrong.

### Fixes (D18–D20)
- **LLM-SQL result contract** (`app/sql_contract.py`): rows accepted only if required
  columns present + numeric types parse, AND they pass a **semantic filter**
  (body_type, capacity_t>=weight_t, payment_terms). Else deterministic fallback with
  `fallback_reason` ∈ {guard_rejected, zero_rows, missing_columns, invalid_values,
  semantic_mismatch}. `sql_path` ∈ {llm_sql, fallback_sql, none}.
- **Route-derived distance:** pricing looks `distance_km` up from `routes`
  (`retrieval.route_distance`), never trusts the model; unknown lane → new
  **no_route** status + deterministic reply. Candidate/fallback query no longer joins
  routes.
- **Eval runner robustness:** each case try/except → `status=error` + exception type,
  run continues; `error_rate` metric; streams one JSON record/case to
  `eval/runs/<provider>_<ts>.jsonl`; `--resume <file>` skips done ids; metrics add
  sql_path + fallback_reason distributions. Table aggregated from jsonl.
- **Docs:** docs/case-sql-contract.md; README updated (eval table, node table,
  result-contract paragraph, mock-vs-real links both cases).

### Verification
- pytest **129 passed**, ruff clean (tests forced to mock via conftest).
- eval (mock, 46): status 100%, error 0%, extraction 100%, clarify P/R 100%, attack
  100%, hallucination 0%, price 100%, SQL path llm/fallback = 18/5, fallback reasons
  zero_rows=5. results_mock.md regenerated.
- Real model NOT invoked this session (user runs it). dataset no_route_* now expect
  no_route.

### Overnight real-model run (PowerShell), with resume
```powershell
$env:LLM_PROVIDER = "ollama"; $env:LLM_MODEL = "qwen2.5:3b"; $env:OLLAMA_TIMEOUT = "1800"
# first run (writes eval/runs/ollama_<timestamp>.jsonl):
python -m eval.run_eval --provider ollama --ids-file eval/subset_cpu.txt
# if interrupted, resume by pointing --resume at that file (newest shown here):
$f = (Get-ChildItem eval/runs/ollama_*.jsonl | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
python -m eval.run_eval --provider ollama --ids-file eval/subset_cpu.txt --resume $f
```

---

## Status: S10 "Real-model hardening" done (2026-10-05)

### The bug (found on real model)
ollama/qwen2.5:7b on "нужно отвезти 12 тонн труб из минска в москву ..." returned
status=no_options BUT the responder showed two invented carriers (ООО "Автотрейдинг"
50 000, ФКУ "Транспорт" 48 000). Mock hid it. Root cause: SQL agent found 0 rows
(small model echoed inflected cities минска/москву), and the responder let the LLM
write the reply even with empty options → fabrication.

### Fixes (all provider-independent)
- **Grounding (D14):** no_options → deterministic template, no LLM. With options →
  LLM reply checked by `guardrails/output_guard.py` (every carrier+price must be in
  state.options); violation → deterministic fallback + `output_guard_blocked` trace.
- **Normalization + fallback (D15):** `app/normalize.py` canonicalizes cities/enums
  after extractor; `app/retrieval.py` parameterized fallback query runs when LLM SQL
  fails or returns 0 rows for a complete request; trace records
  sql_path=llm_sql|fallback_sql|none.
- **Ollama (D16):** OLLAMA_TIMEOUT=600, OLLAMA_KEEP_ALIVE=30m, OLLAMA_NUM_CTX=8192.
- **CLI --verbose:** prints extraction, SQL attempts + guard verdicts, sql_path,
  row/option counts, steps.
- **Eval:** hallucination_rate metric; flags --provider/--limit/--ids/--ids-file;
  writes results_<provider>.md; +4 no_route cases (46 total); eval/subset_cpu.txt.
- **Seed realism (D17):** country-correct legal forms + phones (BY +375 25/29/33/44,
  RU +7, LT UAB +370, PL Sp. z o.o. +48). Recomputed 3 pinned eval prices.
- **Docs:** docs/case-hallucination.md; README "Mock vs real model".

### Verification
- pytest **115 passed**, ruff clean (tests forced to mock regardless of local .env).
- eval (mock, 46 cases): status 100%, extraction 100%, clarify P/R 100%, attack
  block 100%, offtopic 100%, **hallucination 0%**, price 100%, SQL path llm/fallback
  = 18/5. results_mock.md regenerated.

### Real-model control run (ollama qwen2.5:7b, CPU)
Command:
```
LLM_PROVIDER=ollama LLM_MODEL=qwen2.5:7b \
  python -m app.cli --verbose "нужно отвезти 12 тонн труб из минска в москву в четверг, тент, оплата безнал"
```
Result: ran 00:37:20 → 01:13:54 (~36 min). The pipeline advanced through
input_guard → extractor → sql_agent → pricing and **reached the `responder` node
with options in hand** (so the old no_options/hallucination bug did NOT recur). The
final `responder` LLM call then exceeded the configured 600s per-call timeout:

```
httpx.ReadTimeout: timed out
During task with name 'responder' and id '...'
  File "app/nodes/responder.py", line 29, in responder_node
    llm_reply = provider.compose_reply(request, top)
  File "app/llm/ollama_provider.py", line 28, in _chat
    resp = httpx.post(...)
EXIT=0 (process exit; the graph raised inside the responder step)
```

Interpretation: every earlier LLM call (attack-classify, extract, SQL) completed
under 600s; only the responder generation on CPU exceeded it. This is a
**performance limit of a 7B model on CPU**, not a logic bug — the grounding /
normalization / fallback fixes worked right up to the final generation. The timeout
is env-configurable by design (D16): raise `OLLAMA_TIMEOUT` (e.g. 1200) for CPU, or
use a faster model (e.g. `llama3.2:3b`, which is installed) for an end-to-end reply.
Per the task's "call the real model minimally" rule and the spec'd 600s default, the
default was left unchanged and the run was not repeated.

---

## Status: COMPLETE (S9 done, 2026-10-04)

### Final verification (clean rebuild)
- Deleted data/, re-seeded from scratch: carriers=15, trucks=40, routes=44, rates=25.
- pytest: **90 passed**. ruff: **all checks passed**.
- eval (mock, 42 cases): status 100%, extraction 100% (all fields), clarify P/R 100%,
  SQL validity 100%, attack block 100% (n=12), offtopic 100%, price 100% (n=3),
  latency p50 ~9 ms / p95 ~37 ms.
- Docker: image build NOT verified locally (Docker Desktop engine not running);
  Dockerfile + compose reviewed. User can run `docker compose up --build`.

### Manual checks recommended before publishing
- Start Docker Desktop and run `docker compose up --build`; hit /health and /dispatch.
- (Optional) Try a real model: set LLM_PROVIDER + key in .env, rerun eval, update
  the README metrics table / results.md for the real-model column.
- Create the GitHub repo under q6066697 and push (push was intentionally not done).

---

## Status: S8 done (2026-10-04)

### Done (S8)
- README.md: EN with Mermaid graph diagram, node table, why-deterministic-pricing,
  guardrails explanation, eval metrics table (from results.md), quick start
  (mock/real/Docker), limitations, Author (https://github.com/q6066697), short RU
  section.
- NOTE: `docker build` could not be run here — Docker Desktop engine not running
  (CLI present, daemon unreachable). Dockerfile/compose reviewed; build left for the
  user via `docker compose up --build`.

### Next (S9)
- Final full pytest + eval run, update PROGRESS, print summary.

---

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
