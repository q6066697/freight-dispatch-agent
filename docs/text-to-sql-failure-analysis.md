# Text-to-SQL failure analysis — qwen2.5:3b on CPU

What the model's own SQL actually looked like, taxonomised from a full real run.

- Run: `python -m eval.run_eval --provider ollama` (survived a machine shutdown,
  continued with `--resume`) → `eval/runs/ollama_20261006_221545.jsonl`.
- Model: **qwen2.5:3b** via Ollama, **CPU-only**. 23 of 46 cases reached the SQL agent.
- **LLM-SQL accepted: 0 / 23.** Every case fell back to the deterministic query — yet
  status accuracy was 100%, hallucination 0%, price correctness 100%. The guard +
  contract + fallback turned uniformly bad SQL into uniformly correct retrieval.

Records now store each attempt's raw SQL and the guard/contract verdict (D24), so this
is read straight from the run, not reconstructed.

## Per-case outcome (final fallback reason)

| Reason | n | Cases |
|---|---|---|
| `missing_columns` | 9 | normal_02, _04, _09, _11, _13, _14, _15, _17, _18 |
| `zero_rows` | 9 | normal_01, _05, _06, _08, _12, _16, edge_01, no_route_01, no_route_03 |
| `guard_rejected` | 5 | normal_03, _07, _10, no_route_02, no_route_04 |

(For `edge_01` and the `no_route_*` cases, 0 rows is the *correct* answer — there is no
suitable truck / no such lane — so the fallback and the model agree there; those are
not model mistakes, the pipeline still returns the right `no_options` / `no_route`.)

## Failure taxonomy

| # | Failure mode | What the model did | Typical outcome |
|---|---|---|---|
| 1 | **payment ↔ currency confusion** | `JOIN rates r ON … AND r.currency = 'noncash'` — `currency` is `'RUB'`; payment terms live on `carriers` | `zero_rows` |
| 2 | **wrong output shape** | aliased columns (`c.name AS carrier_name`), omitted `plate` / `current_city` / `distance_km` / `payment_terms` | `missing_columns` |
| 3 | **non-existent join key / column** | `JOIN rates r ON t.id = r.truck_id`, `c.rating >= r.min_rating`, `r.distance_km`, `t.distance_km` — none exist in the schema | exec error → `guard_rejected` |
| 4 | **hallucinated geo/PostGIS** | `ST_Distance_Sphere(MakePoint(-27.6, 38.4), …)`, `ST_PointFromText`, `sdo_geometry`, invented lat/long over city-name text | parse error → `guard_rejected` |
| 5 | **markdown / prose wrapping** | answer wrapped in ```` ```sql … ``` ```` | guard: *only SELECT allowed* / *multiple statements* → `guard_rejected` |
| 6 | **malformed syntax** | unbalanced parens, `WHERE` before `JOIN`, stray `?='Минск'` param text, broken `CASE` | parse error → `guard_rejected` |
| 7 | **LIKE on the cargo word** | `t.body_type LIKE '%трубы%'`, `LIKE '%реф%'` — filtering body type by the freight word | contributes to `zero_rows` |
| 8 | **omitted route join** | no join to `routes` at all, so no `distance_km` in the result | `missing_columns` |

The dominant pattern: even when the SQL is syntactically fine, the model does not
respect the schema (column names, which table holds payment vs currency, which key
joins `rates`) or the required output columns — so the rows are unusable even when
non-empty.

## Representative SQL (verbatim, trimmed)

**1 — payment/currency confusion → zero rows** (`normal_05`):
```sql
JOIN rates r ON t.body_type = r.body_type AND r.currency = 'noncash'
WHERE t.status = 'free' AND t.body_type = 'изотерм' AND t.capacity_t >= 8
```

**2 — wrong output shape → missing_columns** (`normal_13`): guard-valid, runs, but no
`plate` / `current_city` / `distance_km` / `payment_terms`, and `carrier` is aliased away:
```sql
SELECT c.id AS carrier_id, c.name AS carrier_name, c.rating, c.payment_terms,
       r.rate_per_km, r.min_price, r.currency
FROM carriers c JOIN trucks t ON c.id = t.carrier_id
JOIN rates r ON t.body_type = r.body_type AND t.capacity_t >= 12
WHERE t.status = 'free' AND t.body_type = 'тент' ORDER BY r.rate_per_km LIMIT 5
```

**3 — non-existent column → execution failure** (`normal_03`): `rates` has no
`truck_id`; the query passes the guard but errors at execution:
```sql
JOIN rates r ON t.id = r.truck_id
JOIN routes rt ON t.current_city = rt.origin AND rt.destination = 'Вильнюс'
```

**4 — hallucinated geo function → guard parse-reject** (`no_route_04`):
```sql
… AND SQRT(POWER(ST_Distance_Sphere(MakePoint(-79.1832, 50.445),
      MakePoint(23.9928, 53.715)), 2) * t.volume_m3 / 100 <= t.capacity_t * r.rate_per_km
```

**5 — markdown fence → guard "only SELECT allowed"** (`normal_07`):
````text
```sql
SELECT c.id AS carrier_id, … FROM carriers c JOIN trucks t … LIMIT 10
```
````

## A note on `guard_rejected`

`guard_rejected` in these records means *no model query produced usable executed
rows*. That bundles two causes: queries the guard rejected outright (modes 4–6), and
guard-passing queries that then failed at execution (mode 3 — e.g. `rates.truck_id`,
unbound `:weight_t`, `WHERE` before `JOIN`). Splitting the label into `guard_rejected`
vs `exec_error` would make this crisper; it is listed in the README Future work (no
logic was changed in this stage — the fallback behaviour is already correct).

## Two full runs compared (221405 vs 221545)

| | 221405 (n=46) | 221545 (n=46) |
|---|---|---|
| Status accuracy | 97.8% | **100%** |
| Errors | 1 (`normal_17` ValidationError) | 0 |
| SQL path llm / fallback | 0 / 22 | 0 / 23 |
| `guard_rejected` / `missing_columns` / `zero_rows` | 5 / 8 / 9 | 5 / 9 / 9 |
| Hallucination | 0% | 0% |
| Price correctness | 100% | 100% |

The two runs are remarkably stable: identical `guard_rejected` and `zero_rows` counts,
`llm_sql` accepted 0 times in both, hallucination 0% in both. The single difference is
`normal_17`, which went from a `ValidationError` crash to a clean `ok` (via fallback) —
the D22 extractor repair/coercion fix, now confirmed on the real model. `missing_columns`
rose 8 → 9 precisely because `normal_17` now completes and lands there.

---

## Кратко по-русски

Полный реальный прогон qwen2.5:3b (CPU, пережил выключение машины и продолжен через
`--resume`): до SQL-агента дошли 23 кейса, и **ни один** SQL модели не был принят
(0/23) — всё вытянул детерминированный fallback, при этом status 100%, галлюцинаций
0%, цена 100%. Таксономия ошибок text-to-SQL на 3B: путаница payment/currency
(`r.currency='noncash'`), неверная форма результата (нет нужных колонок, `carrier`
переименован), несуществующие колонки/ключи (`rates.truck_id`, `r.min_rating`),
выдуманные гео-функции PostGIS (`ST_Distance_Sphere`, `MakePoint`), обёртка в
```` ```sql ````, битый синтаксис, `LIKE` по грузу вместо кузова, отсутствие join к
`routes`. Метка `guard_rejected` объединяет и отклонённые guard'ом запросы, и
прошедшие guard, но упавшие на выполнении — это неточность, вынесена в Future work
(логику на этом этапе не трогали). Два полных прогона стабильны; единственная разница —
`normal_17` перестал падать (фикс D22 подтверждён на реальной модели).
