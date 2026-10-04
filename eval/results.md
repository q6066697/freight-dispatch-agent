# Eval results

- Provider: **mock**
- Cases: **42**
- Generated: 2026-10-04

## Headline metrics

| Metric | Value |
|---|---|
| Status accuracy | 100.0% |
| Extraction accuracy (overall) | 100.0% |
| Clarify precision | 100.0% |
| Clarify recall | 100.0% |
| SQL validity rate | 100.0% |
| SQL guard-block rate | 0.0% |
| Attack block rate (n=12) | 100.0% |
| Off-topic block rate | 100.0% |
| Price correctness (n=3) | 100.0% |
| Latency p50 | 9.1 ms |
| Latency p95 | 43.9 ms |

## Extraction accuracy by field

| Field | Accuracy |
|---|---|
| origin | 100.0% |
| destination | 100.0% |
| weight_t | 100.0% |
| body_type | 100.0% |
| payment | 100.0% |
| urgent | 100.0% |
| load_type | 100.0% |

SQL: 19 generated queries across 19 cases reached the SQL agent; each was validated by the guard before read-only execution.
