"""Evaluation harness.

Runs every labeled case in dataset.jsonl through the graph (mock by default, fully
offline) and reports:
  - extraction field accuracy (per field + overall)
  - clarify precision / recall
  - SQL validity rate and guard-block share
  - attack block rate (target 100%)
  - price correctness vs. pinned reference values
  - latency p50 / p95

Prints a table and writes eval/results.md. Run:  python -m eval.run_eval
"""

from __future__ import annotations

import json
import math
import time
from datetime import date
from pathlib import Path

from app.graph import build_graph, to_response
from app.llm import get_provider

DATASET = Path(__file__).with_name("dataset.jsonl")
RESULTS = Path(__file__).with_name("results.md")

FIELDS = [
    "origin", "destination", "weight_t", "volume_m3",
    "body_type", "payment", "urgent", "load_type",
]
# Cases that run extraction (i.e. not attacks/offtopic refused up front).
EXTRACTION_CATEGORIES = {"normal", "slang", "incomplete", "edge"}


def load_cases() -> list[dict]:
    cases = []
    for line in DATASET.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            cases.append(json.loads(line))
    return cases


def _norm(v):
    return v.strip().lower() if isinstance(v, str) else v


def _percentile(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    k = max(0, math.ceil(p / 100 * len(s)) - 1)
    return s[k]


def run(provider_name: str | None = None) -> dict:
    # Default to the offline mock explicitly, independent of any local .env.
    provider = get_provider(provider_name or "mock")
    graph = build_graph(provider)
    cases = load_cases()

    latencies: list[float] = []
    field_hits = {f: [0, 0] for f in FIELDS}  # field -> [matches, applicable]
    clarify = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    attack_total = attack_blocked = 0
    offtopic_total = offtopic_blocked = 0
    sql_total = sql_ok = sql_blocked = 0
    sql_cases = 0
    price_total = price_ok = 0
    status_hits = 0

    for case in cases:
        exp = case["expected"]
        t0 = time.perf_counter()
        final = graph.invoke({"text": case["text"]})
        latencies.append((time.perf_counter() - t0) * 1000)
        resp = to_response(final)

        # status accuracy
        if resp.status == exp["status"]:
            status_hits += 1

        # extraction accuracy
        gold_fields = exp.get("fields", {})
        if case["category"] in EXTRACTION_CATEGORIES and gold_fields:
            got = resp.request
            for f, gold_v in gold_fields.items():
                if f not in field_hits:
                    continue
                field_hits[f][1] += 1
                got_v = getattr(got, f, None) if got else None
                if _norm(got_v) == _norm(gold_v):
                    field_hits[f][0] += 1

        # clarify precision/recall (over extraction-path cases)
        if case["category"] in EXTRACTION_CATEGORIES:
            want = exp["status"] == "clarify"
            pred = resp.status == "clarify"
            if want and pred:
                clarify["tp"] += 1
            elif not want and pred:
                clarify["fp"] += 1
            elif want and not pred:
                clarify["fn"] += 1
            else:
                clarify["tn"] += 1

        # attack / offtopic block rate
        if case["category"] == "attack":
            attack_total += 1
            if resp.status == "refused":
                attack_blocked += 1
        if case["category"] == "offtopic":
            offtopic_total += 1
            if resp.status == "refused":
                offtopic_blocked += 1

        # SQL metrics
        attempts = final.get("sql_attempts") or []
        if attempts:
            sql_cases += 1
            for a in attempts:
                sql_total += 1
                if a["ok"]:
                    sql_ok += 1
                else:
                    sql_blocked += 1

        # price correctness vs pinned reference
        if "price_rub" in exp and exp["price_rub"] is not None:
            price_total += 1
            if resp.options and abs(resp.options[0].price - exp["price_rub"]) < 1.0:
                price_ok += 1

    # assemble metrics
    def ratio(n, d):
        return (n / d) if d else None

    field_acc = {
        f: ratio(hits, appl) for f, (hits, appl) in field_hits.items() if appl
    }
    overall_matches = sum(h for h, _ in field_hits.values())
    overall_appl = sum(a for _, a in field_hits.values())

    prec = ratio(clarify["tp"], clarify["tp"] + clarify["fp"])
    rec = ratio(clarify["tp"], clarify["tp"] + clarify["fn"])

    metrics = {
        "provider": provider.name,
        "n_cases": len(cases),
        "status_accuracy": ratio(status_hits, len(cases)),
        "field_accuracy": field_acc,
        "field_accuracy_overall": ratio(overall_matches, overall_appl),
        "clarify_precision": prec if prec is not None else 1.0,
        "clarify_recall": rec if rec is not None else 1.0,
        "sql_cases": sql_cases,
        "sql_attempts": sql_total,
        "sql_validity_rate": ratio(sql_ok, sql_total),
        "sql_guard_block_rate": ratio(sql_blocked, sql_total),
        "attack_block_rate": ratio(attack_blocked, attack_total),
        "attack_total": attack_total,
        "offtopic_block_rate": ratio(offtopic_blocked, offtopic_total),
        "price_cases": price_total,
        "price_correctness": ratio(price_ok, price_total),
        "latency_p50_ms": _percentile(latencies, 50),
        "latency_p95_ms": _percentile(latencies, 95),
    }
    return metrics


def _fmt_pct(x) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def render_markdown(m: dict) -> str:
    lines = [
        "# Eval results",
        "",
        f"- Provider: **{m['provider']}**",
        f"- Cases: **{m['n_cases']}**",
        f"- Generated: {date.today().isoformat()}",
        "",
        "## Headline metrics",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Status accuracy | {_fmt_pct(m['status_accuracy'])} |",
        f"| Extraction accuracy (overall) | {_fmt_pct(m['field_accuracy_overall'])} |",
        f"| Clarify precision | {_fmt_pct(m['clarify_precision'])} |",
        f"| Clarify recall | {_fmt_pct(m['clarify_recall'])} |",
        f"| SQL validity rate | {_fmt_pct(m['sql_validity_rate'])} |",
        f"| SQL guard-block rate | {_fmt_pct(m['sql_guard_block_rate'])} |",
        f"| Attack block rate (n={m['attack_total']}) | {_fmt_pct(m['attack_block_rate'])} |",
        f"| Off-topic block rate | {_fmt_pct(m['offtopic_block_rate'])} |",
        f"| Price correctness (n={m['price_cases']}) | {_fmt_pct(m['price_correctness'])} |",
        f"| Latency p50 | {m['latency_p50_ms']:.1f} ms |",
        f"| Latency p95 | {m['latency_p95_ms']:.1f} ms |",
        "",
        "## Extraction accuracy by field",
        "",
        "| Field | Accuracy |",
        "|---|---|",
    ]
    for f in FIELDS:
        if f in m["field_accuracy"]:
            lines.append(f"| {f} | {_fmt_pct(m['field_accuracy'][f])} |")
    lines.append("")
    lines.append(
        f"SQL: {m['sql_attempts']} generated queries across {m['sql_cases']} "
        "cases reached the SQL agent; each was validated by the guard before "
        "read-only execution."
    )
    lines.append("")
    return "\n".join(lines)


def print_table(m: dict) -> None:
    print(f"\n=== Eval ({m['provider']}, {m['n_cases']} cases) ===")
    rows = [
        ("Status accuracy", _fmt_pct(m["status_accuracy"])),
        ("Extraction (overall)", _fmt_pct(m["field_accuracy_overall"])),
        ("Clarify precision", _fmt_pct(m["clarify_precision"])),
        ("Clarify recall", _fmt_pct(m["clarify_recall"])),
        ("SQL validity", _fmt_pct(m["sql_validity_rate"])),
        ("SQL guard-block", _fmt_pct(m["sql_guard_block_rate"])),
        (f"Attack block (n={m['attack_total']})", _fmt_pct(m["attack_block_rate"])),
        ("Off-topic block", _fmt_pct(m["offtopic_block_rate"])),
        (f"Price correctness (n={m['price_cases']})", _fmt_pct(m["price_correctness"])),
        ("Latency p50", f"{m['latency_p50_ms']:.1f} ms"),
        ("Latency p95", f"{m['latency_p95_ms']:.1f} ms"),
    ]
    width = max(len(r[0]) for r in rows)
    for name, val in rows:
        print(f"  {name.ljust(width)} : {val}")
    print("  --- extraction by field ---")
    for f in FIELDS:
        if f in m["field_accuracy"]:
            print(f"  {f.ljust(width)} : {_fmt_pct(m['field_accuracy'][f])}")


def main() -> dict:
    m = run()
    print_table(m)
    RESULTS.write_text(render_markdown(m), encoding="utf-8")
    print(f"\nWrote {RESULTS}")
    return m


if __name__ == "__main__":
    main()
