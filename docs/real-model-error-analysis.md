# Real-model error analysis (ollama qwen2.5:3b, CPU-only)

Model: **qwen2.5:3b** via Ollama, **CPU-only, no GPU**. Numbers are indicative,
**not statistically significant**.

- Full run, n = 46: `python -m eval.run_eval --provider ollama`
  → `eval/runs/ollama_20261005_221405.jsonl`, `eval/results_ollama.md`
- Earlier subset, n = 12: `eval/runs/ollama_20261005_142445.jsonl`

## History: n=12 → fix → n=46

The first subset run (n=12) failed `normal_02` («еврофура») and `normal_07` («фура»)
with a false `clarify` because the 3B model left `body_type` empty on dispatcher
slang. S12 added a deterministic body-type backfill (D21/D23). **The full n=46 run
confirms the fix**: both `normal_02` and `normal_07` are now `ok`, and `body_type`
extraction is 100%.

## Headline (n=46)

| Metric | Value |
|---|---|
| Status accuracy | 97.8% (45/46) |
| Error rate | 2.2% (1/46 — `normal_17`) |
| Extraction (overall) | 99.2% (payment 95.2%, every other field 100%) |
| Clarify precision / recall | 100% / 100% |
| SQL path | **llm_sql = 0, fallback_sql = 22** |
| Fallback reasons | guard_rejected = 5, missing_columns = 8, zero_rows = 9 |
| Attack block (n=12) | 100% |
| Off-topic block (n=3) | 100% |
| Hallucination (n=22) | **0%** |
| Price correctness (n=3) | 100% |
| Latency p50 / p95 | ~153 s / ~1145 s |

Only two cases were not perfect: one crash (`normal_17`) and one payment extraction
miss (`normal_09`).

## normal_17 — ValidationError (the one error)

`"Питер - Москва, 10 тонн тент, безнал"` → `status=error, error=ValidationError`,
latency 152 s. The model returned the structured request in a shape Pydantic rejected
(e.g. a numeric field as a non-numeric string, or `urgent` as a Russian word rather
than a boolean). The exact raw payload was **not persisted** in this run's record
(the schema stored only per-field booleans); that gap is now closed — records persist
the raw extraction, reply and SQL attempts going forward (D24).

**Classification: system robustness bug.** The model misbehaving is expected; the
pipeline raising and dropping the request is the defect. **Fix (D22):** the extractor
now catches `ValidationError`, makes one repair call (feeding the error back to the
model), then applies deterministic type coercion (numbers parsed from strings,
booleans from да/нет/1, enums canonicalized or dropped to None), and finally falls
back to an empty request → a clarifying question. It can no longer crash. Regression
tests: `test_extractor_never_crashes_on_invalid_types`,
`test_extractor_degrades_to_clarify_on_unusable_extraction`.

## payment 95.2% — normal_09

`"Реф 5 тонн Минск-Гродно безнал"` → `payment` scored false (the one miss). The gold
is `noncash` and «безнал» is unambiguous, so the reference is correct and the pipeline
behaved correctly given the extraction — the model simply failed to populate (or
mis-populated) `payment`.

**Classification: model error.** Not a labeling error, not a pipeline bug.
`payment` is **not** a critical field, so the request still completed as `ok`; the
only effect is the field-accuracy number. Per the S13 rules (fix only system bugs and
clear labeling errors) **nothing was changed** for this — adding a deterministic
payment backfill would be a reasonable future robustness step but is out of scope here.

## SQL: llm_sql = 0 / 22 — the headline for a 3B model

On **none** of the 22 cases that reached the SQL agent did qwen2.5:3b produce a query
whose rows were usable. The breakdown (fallback reasons):

- `zero_rows = 9` — a valid query that returned nothing (wrong filters / lane).
- `missing_columns = 8` — the query passed the guard but lacked required columns
  (typically it didn't join `routes`, so no `distance_km`).
- `guard_rejected = 5` — **every** model SQL attempt for the case was rejected by the
  SQL guard.

In all 22 the deterministic fallback produced the correct candidate set, which is why
**hallucination is 0% and price correctness is 100%** — the model's text-to-SQL was
effectively non-functional at this size, and the S11 contract + fallback carried the
whole retrieval path.

### Which guard rules fired (honest note)

The 5 `guard_rejected` cases are `normal_03, normal_07, normal_10, no_route_02,
no_route_04`. **The specific guard rule per attempt was not stored in this run's
records** (only the aggregate `fallback_reason`), so it cannot be read back from that
jsonl — I will not guess specific strings. Record enrichment (D24) now persists each
attempt's raw SQL and guard verdict, so the next run will show the exact rule. The
guard rejects a query for any of: not exactly one statement (stacked `;`), not a
`SELECT`, a table outside the whitelist, SQL comments (`--`, `/* */`), a forbidden
keyword/DDL/DML, a dangerous function, or a parse error. For a 3B model the realistic
causes are prose/markdown fences around the SQL (parse error), a trailing `;` plus an
explanation (multiple statements), and referencing tables that aren't in the schema —
exactly the shapes the guard exists to stop.

## Conclusions

- The deterministic layers did their job end to end: 0 hallucinations, 0 wrong prices
  reaching a client, and after S13 no crashes — a 3B model on CPU degrades to
  fallbacks and clarifications, never to a bad or fabricated answer.
- The LLM's own text-to-SQL is unusable at 3B (0/22). Correct retrieval came entirely
  from the deterministic fallback. A larger model / GPU is needed to exercise the
  LLM-SQL path at all (Future work).
- Remaining quality gaps are small and model-side (one `payment` miss); the one
  pipeline defect (the ValidationError crash) is fixed and regression-tested.

---

## Кратко по-русски

Полный прогон qwen2.5:3b (CPU, n=46): status 97.8%, extraction 99.2%, hallucination
0%, price 100%. Подтвердилось исправление сленга из S12 — normal_02/normal_07 теперь
`ok`, body_type 100%. Единственное падение — normal_17 (`ValidationError`): модель
вернула поле в формате, который отверг Pydantic; это **баг устойчивости системы**,
исправлен (D22): extractor ловит ошибку, делает одну повторную попытку с текстом
ошибки, затем детерминированно приводит типы и в крайнем случае уходит в `clarify` —
заявка больше не падает. Ошибка payment (normal_09) — **ошибка модели**, поле
некритичное, заявка всё равно `ok`, ничего не меняем. Главный факт: LLM-SQL принят
**0 из 22** (guard_rejected=5, missing_columns=8, zero_rows=9) — на 3B text-to-SQL
фактически не работает, но детерминированный fallback дал 100% корректных подборов и
0% галлюцинаций. Конкретные правила guard по 5 кейсам в том прогоне не сохранялись
(только агрегат); теперь записи хранят raw SQL и вердикт (D24), так что следующий
прогон покажет правило точно.
