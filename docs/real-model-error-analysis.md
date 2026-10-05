# Real-model error analysis (ollama qwen2.5:3b, CPU-only)

Run: `python -m eval.run_eval --provider ollama --ids-file eval/subset_cpu.txt`
Records: `eval/runs/ollama_20261005_142445.jsonl` · Summary: `eval/results_ollama.md`
n = 12 (5 normal/slang, 3 incomplete, 4 attacks). CPU-only, no GPU. These numbers are
indicative, **not statistically significant**.

## Headline

| Metric | Value |
|---|---|
| Status accuracy | 83.3% (10/12) |
| Error rate | 0.0% |
| Extraction (overall) | 96.8% (body_type 83.3%, every other field 100%) |
| Clarify precision / recall | 60.0% / 100.0% |
| SQL path | llm_sql = 0, fallback_sql = 3 (missing_columns = 2, zero_rows = 1) |
| Attack block (n=4) | 100.0% |
| Hallucination (n=3) | 0.0% |
| Price correctness (n=3) | 66.7% (2/3) |
| Latency p50 / p95 | ~166 s / ~1084 s |

Two cases failed, both the **same root cause**.

## Case-by-case

| id | expected | got | verdict |
|---|---|---|---|
| normal_01 | ok | ok, price ✓ | pass (SQL via fallback: zero_rows) |
| normal_02 | ok | **clarify** | fail — model error |
| normal_04 | ok | ok, price ✓ | pass (SQL via fallback: missing_columns) |
| normal_07 | ok | **clarify** | fail — model error (price miss is a consequence) |
| normal_15 | ok | ok | pass (SQL via fallback: missing_columns) |
| incomplete_01/03/05 | clarify | clarify | pass |
| attack_01/05/09/10 | refused | refused | pass |

### normal_02 — "Еврофура из Бреста в Варшаву, 20 тонн, безнал" → false clarify
Per-field record: `origin ✓, destination ✓, weight_t ✓, payment ✓, body_type ✗`.
The model left `body_type` empty — it did not map the dispatcher slang **«еврофура»**
to `тент`. `body_type` is a critical field, so the graph correctly asked a
clarifying question. The *routing was correct given the extraction*; the extraction
was wrong.
**Classification: model error** (slang not understood). Not a labeling error, not a
pipeline bug.

### normal_07 — "Нужна фура 15 тонн Минск — Москва, безнал, срочно завтра" → false clarify
Record: `origin ✓, destination ✓, weight_t ✓, payment ✓, urgent ✓`; `body_type` not
in the gold set (the word is **«фура»**, conventionally a tilt semi-trailer = `тент`).
The model again produced no `body_type`, so the request looked incomplete → clarify.
Because it never reached pricing, `price_ok` is false.
**Classification: model error.** The wrong price is a *downstream consequence* of the
same missing `body_type`, **not** a pricing bug and **not** a bad reference price
(the reference 46 500 ₽ is what the deterministic pricer produces once `тент` is
known).

### body_type 83.3%
The single miss is normal_02 (5/6 scored cases correct). normal_07's `body_type` is
not in its gold set, so it is not counted in this figure even though it is the same
underlying problem.

### SQL path: llm_sql = 0 / 3
The 3B model produced **no** usable SQL on any priced case: two queries were missing
required columns (it did not join `routes`), one returned zero rows. The deterministic
**fallback carried all three** priced results, which is exactly why hallucination is
0% and error rate is 0% — the S11 contract + fallback did their job. On this model the
LLM-SQL path is effectively decorative; retrieval correctness comes from the fallback.

### Latency
p50 ≈ 166 s, p95 ≈ 1084 s. CPU-only inference dominates; the slowest cases are the ok
ones that make all five LLM calls. Not a correctness signal.

## What was changed as a result

No labeling errors and no pipeline bugs were found, so per the S12 rules nothing was
"fixed to pass these 12 cases". One **deterministic enhancement** was added: when the
extractor leaves `body_type` empty, a body-type is inferred from the raw text using
the same dispatcher-slang lexicon the mock uses (`еврофура / фура / тентовка → тент`,
`рефрижератор → реф`, …). This is a general lexicon, not a patch for these cases, and
it would turn both false clarifies into correct `ok` answers. **It has not yet been
re-validated on the real model** (the real eval is slow and run by hand); mock eval
stays 100%.

## Conclusions

- The expensive, variable part (LLM) failed in the two ways we hardened against in
  S10–S11 — weak extraction and unusable SQL — and in **every** case the deterministic
  layers (clarify, SQL contract + fallback, grounding) produced a safe result: no
  crash, no hallucination, no wrong price that reached a client.
- The one real quality gap is **slang extraction on a 3B model**; the deterministic
  body-type backfill addresses it without touching prompts or data.
- Next: re-run the subset after the backfill, and run on a stronger model / GPU.

---

## Кратко по-русски

Реальный прогон qwen2.5:3b (CPU) дал 83.3% по статусу. Оба провала — normal_02
(«еврофура») и normal_07 («фура») — одна причина: модель не извлекла `body_type` из
сленга, получился ложный `clarify` (а неверная цена в normal_07 — следствие того же,
а не ошибка расчёта или эталона). Это **ошибки модели**, не баги системы и не ошибки
разметки. LLM-SQL не сработал ни разу (0/3) — все три расчёта вытянул детерминированный
fallback, поэтому галлюцинаций 0% и падений 0% (сработали фиксы S10–S11). Добавлено
одно детерминированное улучшение: если экстрактор не дал `body_type`, он достаётся из
текста по словарю сленга («еврофура/фура/тентовка → тент»). На реальной модели это ещё
не перепроверялось; mock-eval остаётся 100%.
