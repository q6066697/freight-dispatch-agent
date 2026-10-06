# Eval results

- Provider: **ollama**
- Cases: **46**
- Generated: 2026-10-06 03:59

## Headline metrics

| Metric | Value |
|---|---|
| Status accuracy | 97.8% |
| Error rate (n=1) | 2.2% |
| Extraction (overall) | 99.2% |
| Clarify precision | 100.0% |
| Clarify recall | 100.0% |
| SQL path | fallback_sql=22 |
| Fallback reasons | guard_rejected=5, missing_columns=8, zero_rows=9 |
| Attack block (n=12) | 100.0% |
| Off-topic block | 100.0% |
| Hallucination rate (n=22) | 0.0% |
| Price correctness (n=3) | 100.0% |
| Latency p50 | 153300.6 ms |
| Latency p95 | 1145177.8 ms |

## Extraction accuracy by field

| Field | Accuracy |
|---|---|
| origin | 100.0% |
| destination | 100.0% |
| weight_t | 100.0% |
| body_type | 100.0% |
| payment | 95.2% |
| urgent | 100.0% |
| load_type | 100.0% |
