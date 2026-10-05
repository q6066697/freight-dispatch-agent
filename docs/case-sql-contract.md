# Case study: a safe SQL query that was still wrong

## What happened

Running the real eval on a small local model
(`LLM_PROVIDER=ollama`, `qwen2.5:3b`, CPU, ~15 min per full case):

```
python -m eval.run_eval --provider ollama --ids-file eval/subset_cpu.txt
```

The first two cases passed (`normal_01` → ok in 982 s, `normal_02` → clarify in
164 s). The **third case crashed the whole run**:

```
File "app/nodes/pricing_node.py", line 22, in pricing_node
    distance = float(row["distance_km"])
KeyError: 'distance_km'
```

The model's SQL had **passed the SQL guard** (it was a single read-only `SELECT`
over whitelisted tables) and returned rows — but it never joined `routes`, so the
rows had no `distance_km`. Pricing assumed the column was there and blew up, taking
the entire ~20-minute run with it.

Earlier real-model runs showed the same class of problem in other shapes:

- `WHERE r.currency = 'noncash'` — the model confused the **payment** field with the
  **currency** column;
- `WHERE t.body_type LIKE '%трубы%'` — it filtered body type by the *cargo* word;
- no route filter at all, so rows were unrelated to the requested lane.

All of these are **safe** queries (nothing the guard exists to stop) and all are
**wrong**.

## Why it happened

The SQL guard answers one question — *is this query safe to execute?* — and it
answered correctly. But nothing downstream checked the second question: *do these
rows actually mean what pricing/responder assume?* Pricing trusted:

1. that the rows carried every column it reads (`distance_km`, `rate_per_km`, …), and
2. that the distance in the row was the real road distance for the lane.

A 3B model honours neither reliably.

## The fix (D18, D19, D20)

1. **Result contract** (`app/sql_contract.py`). Rows from the model are accepted only
   if every required column is present and the numeric ones parse. A query that
   didn't join `routes` now fails the contract (`missing_columns`) instead of
   reaching pricing.
2. **Semantic filter.** Surviving rows must actually match the request —
   `body_type` equal, `capacity_t ≥ weight_t`, carrier `payment_terms` compatible.
   Rows that don't are dropped; if nothing remains the reason is `semantic_mismatch`.
3. **Deterministic fallback.** When the model's rows are unusable (or it produced no
   working query, or zero rows), `sql_agent` runs the trusted parameterized query and
   records **why** in `fallback_reason ∈ {guard_rejected, zero_rows, missing_columns,
   invalid_values, semantic_mismatch}`. The path taken is in `sql_path`
   (`llm_sql | fallback_sql`).
4. **Route-derived distance.** Pricing no longer reads distance from the row at all —
   it looks `distance_km` up from `routes` by the normalized origin/destination. An
   unknown lane becomes the `no_route` status with its own deterministic reply, not a
   crash and not a guess.
5. **Crash-isolated runner.** Even if some future bug slips through, the eval runner
   now wraps each case in try/except (a failure becomes a `status="error"` record and
   the run continues), streams every record to `eval/runs/<provider>_<ts>.jsonl`, and
   supports `--resume` — so one bad case can never again throw away a multi-hour run.

## How it is verified

- `tests/test_graph.py::test_llm_sql_without_distance_falls_back_no_crash` wires a
  provider whose SQL omits the `routes` join (exactly the real failure) into the full
  graph and asserts `sql_path == "fallback_sql"`, `fallback_reason ==
  "missing_columns"`, and a normal `ok` result — no `KeyError`.
- `tests/test_graph.py::test_semantic_mismatch_falls_back` covers wrong-body rows.
- `tests/test_graph.py::test_no_route_status` covers the unknown-lane path.
- `tests/test_sql_contract.py` unit-tests the contract and the semantic filter.
- `tests/test_eval.py` covers crash isolation (`evaluate_case` on a throwing graph),
  survival of a mid-run exception, and `--resume`.
- The eval report now shows the `sql_path` and `fallback_reason` distributions — the
  headline number for a real model: how often it produced usable SQL vs. how often
  the deterministic fallback had to rescue it, and why.

---

## Кратко по-русски

На реальной модели (ollama/qwen2.5:3b, CPU) eval упал с `KeyError: 'distance_km'` на
третьем кейсе: SQL прошёл guard (безопасный `SELECT`), вернул строки, но модель не
присоединила `routes` — и pricing рухнул. В других прогонах та же модель путала
`payment` с `currency` и фильтровала кузов по слову из груза. Guard проверяет
**безопасность**, но не **корректность**. Исправление: контракт на колонки/типы
результата + семантический фильтр (кузов, грузоподъёмность, форма оплаты);
при нарушении — детерминированный fallback с причиной (`fallback_reason`);
расстояние берётся из таблицы `routes`, а не из ответа модели; неизвестный маршрут →
статус `no_route`. Сам раннер теперь ловит исключения по кейсам, пишет результат
каждого кейса в `eval/runs/*.jsonl` и умеет `--resume`, поэтому один плохой кейс не
рушит весь ночной прогон.
