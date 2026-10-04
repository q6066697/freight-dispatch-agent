# Case study: a real model invented carriers on a no-options request

## What happened

Running the graph on a **real** local model (`LLM_PROVIDER=ollama`,
`qwen2.5:7b`, CPU-only, ~3+ min per LLM call) with the request:

> нужно отвезти 12 тонн труб из минска в москву в четверг, тент, оплата безнал

produced:

```
status=no_options; steps=input_guard>extractor>sql_agent>pricing>responder
```

…but the reply shown to the client contained **two carriers that do not exist** in
the `carriers` table, with made-up prices:

```
1) ООО "Автотрейдинг" — тент. Цена 50 000 руб, срок 3 дня.
2) ФКУ "Транспорт"   — тент. Цена 48 000 руб, срок 3 дня.
```

The `mock` provider had hidden the bug: its reply is a deterministic template, so it
never invented anything, and every mock-mode eval metric was green.

## Why it happened

Two independent weaknesses combined:

1. **The SQL agent returned no rows**, so the state had `options = []`. The small
   model wrote a query that matched nothing — most likely because it echoed the
   inflected city strings from the prompt (`минска`, `москву`) into
   `routes.origin/destination`, which store canonical nominative forms
   (`Минск`, `Москва`).
2. **The responder trusted the LLM to render the reply** even with an empty options
   list. A 7B model, asked to be a helpful dispatcher, "helpfully" fabricated
   plausible carriers and prices to fill the gap. Nothing checked the output against
   the data.

## The fix

Three changes, all provider-independent (see `DECISIONS.md` D14–D15):

1. **Deterministic reply for the empty case.** When there are no options, the
   responder returns a fixed Russian template (`app/reply_templates.py`) and never
   calls the LLM — so it is structurally impossible to name a carrier or price.
2. **Output guard** (`app/guardrails/output_guard.py`). When options *do* exist, the
   LLM composes the reply, then the guard parses it and verifies every carrier name
   and every money amount is present in `state.options`. On any violation the
   responder falls back to a deterministic grounded template and emits an
   `output_guard_blocked` event in the step trace.
3. **City normalization + SQL fallback.** `app/normalize.py` canonicalizes
   inflected/mis-cased cities after extraction; `app/retrieval.py` provides a trusted
   parameterized query that `sql_agent` runs when the model's SQL fails or returns
   zero rows for a complete request. The trace records `sql_path = llm_sql |
   fallback_sql | none`. This removes the false `no_options` at its source.

## How it is verified

- `tests/test_output_guard.py::test_real_hallucination_case_blocked` feeds the exact
  invented reply above against an empty options list and asserts it is blocked.
- `tests/test_graph.py::test_responder_grounds_hallucinated_reply` wires a provider
  that fabricates carriers into the full graph and asserts the client never sees the
  invented names/prices and that `output_guard_blocked` appears in the trace.
- `tests/test_graph.py::test_sql_fallback_when_model_sql_always_invalid` and
  `test_normalization_recovers_inflected_cities` cover the retrieval fixes.
- The eval harness reports a **hallucination rate** — the share of composed replies
  naming a carrier/price absent from options. Target and mock value: **0%**.

---

## Кратко по-русски

На реальной модели (ollama/qwen2.5:7b, CPU) заявка Минск→Москва вернула
`no_options`, но ответчик **придумал двух несуществующих перевозчиков** и цены —
в mock-режиме баг был не виден. Причины: SQL-агент не нашёл строк (маленькая модель
подставляла падежные формы городов в запрос), а ответчик доверял LLM формировать
ответ даже при пустом списке вариантов. Исправление: при отсутствии вариантов ответ
формируется **детерминированным шаблоном без LLM**; при наличии вариантов ответ
проверяет **output guard** (каждый перевозчик и цена должны быть в `options`, иначе
fallback на шаблон и событие `output_guard_blocked` в трейсе); плюс нормализация
городов и детерминированный fallback-SQL убирают ложный `no_options`. Проверяется
юнит-тестами (включая этот самый случай) и метрикой hallucination rate (цель 0%).
