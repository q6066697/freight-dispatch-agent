"""Evaluation harness.

Runs labeled cases in dataset.jsonl through the graph and reports:
  - extraction field accuracy (per field + overall)
  - clarify precision / recall
  - SQL validity rate, guard-block share, and LLM-vs-fallback path split
  - attack block rate (target 100%)
  - off-topic block rate
  - hallucination rate (replies naming a carrier/price absent from options)
  - price correctness vs. pinned reference values
  - latency p50 / p95

Prints a table and writes eval/results_<provider>.md (mock never overwrites real).

Examples:
  python -m eval.run_eval
  python -m eval.run_eval --provider ollama --ids-file eval/subset_cpu.txt
  python -m eval.run_eval --limit 10 --ids normal_01,attack_05
"""

from __future__ import annotations

import argparse
import json
import math
import time
from datetime import date
from pathlib import Path

from app.graph import build_graph, to_response
from app.guardrails.output_guard import check_reply
from app.llm import get_provider

DATASET = Path(__file__).with_name("dataset.jsonl")

FIELDS = [
    "origin", "destination", "weight_t", "volume_m3",
    "body_type", "payment", "urgent", "load_type",
]
# Cases that run extraction (i.e. not attacks/offtopic refused up front).
EXTRACTION_CATEGORIES = {"normal", "slang", "incomplete", "edge", "no_route"}
# Cases that end with a composed reply we can check for hallucinations.
RESPONDED_STATUSES = {"ok", "no_options"}


def load_cases() -> list[dict]:
    cases = []
    for line in DATASET.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
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


def _ratio(n, d):
    return (n / d) if d else None


def run(
    provider_name: str | None = None,
    *,
    limit: int | None = None,
    ids: list[str] | None = None,
    progress: bool = False,
) -> dict:
    # Default to the offline mock explicitly, independent of any local .env.
    effective = provider_name or "mock"
    provider = get_provider(effective)
    graph = build_graph(provider)

    cases = load_cases()
    if ids:
        wanted = set(ids)
        cases = [c for c in cases if c["id"] in wanted]
    if limit:
        cases = cases[:limit]

    latencies: list[float] = []
    field_hits = {f: [0, 0] for f in FIELDS}
    clarify = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    attack_total = attack_blocked = 0
    offtopic_total = offtopic_blocked = 0
    sql_total = sql_ok = sql_blocked = 0
    sql_cases = sql_llm = sql_fallback = 0
    price_total = price_ok = 0
    status_hits = 0
    responded = hallucinated = 0

    for idx, case in enumerate(cases, start=1):
        exp = case["expected"]
        t0 = time.perf_counter()
        final = graph.invoke({"text": case["text"]})
        dt = (time.perf_counter() - t0) * 1000
        latencies.append(dt)
        resp = to_response(final)

        if progress:
            print(f"[{idx}/{len(cases)}] {case['id']:<14} "
                  f"{resp.status:<10} {dt/1000:6.1f}s", flush=True)

        if resp.status == exp["status"]:
            status_hits += 1

        gold_fields = exp.get("fields", {})
        if case["category"] in EXTRACTION_CATEGORIES and gold_fields:
            got = resp.request
            for f, gold_v in gold_fields.items():
                if f not in field_hits:
                    continue
                field_hits[f][1] += 1
                if _norm(getattr(got, f, None) if got else None) == _norm(gold_v):
                    field_hits[f][0] += 1

        if case["category"] in EXTRACTION_CATEGORIES:
            want = exp["status"] == "clarify"
            pred = resp.status == "clarify"
            key = ("tp" if pred else "fn") if want else ("fp" if pred else "tn")
            clarify[key] += 1

        if case["category"] == "attack":
            attack_total += 1
            attack_blocked += resp.status == "refused"
        if case["category"] == "offtopic":
            offtopic_total += 1
            offtopic_blocked += resp.status == "refused"

        attempts = final.get("sql_attempts") or []
        if attempts:
            sql_cases += 1
            for a in attempts:
                sql_total += 1
                sql_ok += bool(a["ok"])
                sql_blocked += not a["ok"]
        path = final.get("sql_path")
        sql_llm += path == "llm_sql"
        sql_fallback += path == "fallback_sql"

        # hallucination: does the reply name a carrier/price not in options?
        if resp.status in RESPONDED_STATUSES:
            responded += 1
            opt_dicts = [{"carrier": o.carrier, "price": o.price} for o in resp.options]
            if not check_reply(resp.reply, opt_dicts).ok:
                hallucinated += 1

        if exp.get("price_rub") is not None:
            price_total += 1
            if resp.options and abs(resp.options[0].price - exp["price_rub"]) < 1.0:
                price_ok += 1

    field_acc = {f: _ratio(h, a) for f, (h, a) in field_hits.items() if a}
    prec = _ratio(clarify["tp"], clarify["tp"] + clarify["fp"])
    rec = _ratio(clarify["tp"], clarify["tp"] + clarify["fn"])

    return {
        "provider": provider.name,
        "n_cases": len(cases),
        "status_accuracy": _ratio(status_hits, len(cases)),
        "field_accuracy": field_acc,
        "field_accuracy_overall": _ratio(
            sum(h for h, _ in field_hits.values()),
            sum(a for _, a in field_hits.values()),
        ),
        "clarify_precision": prec if prec is not None else 1.0,
        "clarify_recall": rec if rec is not None else 1.0,
        "sql_cases": sql_cases,
        "sql_attempts": sql_total,
        "sql_validity_rate": _ratio(sql_ok, sql_total),
        "sql_guard_block_rate": _ratio(sql_blocked, sql_total),
        "sql_llm_path": sql_llm,
        "sql_fallback_path": sql_fallback,
        "attack_block_rate": _ratio(attack_blocked, attack_total),
        "attack_total": attack_total,
        "offtopic_block_rate": _ratio(offtopic_blocked, offtopic_total),
        "hallucination_rate": _ratio(hallucinated, responded),
        "responded": responded,
        "price_cases": price_total,
        "price_correctness": _ratio(price_ok, price_total),
        "latency_p50_ms": _percentile(latencies, 50),
        "latency_p95_ms": _percentile(latencies, 95),
    }


def _fmt_pct(x) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def _rows(m: dict) -> list[tuple[str, str]]:
    return [
        ("Status accuracy", _fmt_pct(m["status_accuracy"])),
        ("Extraction (overall)", _fmt_pct(m["field_accuracy_overall"])),
        ("Clarify precision", _fmt_pct(m["clarify_precision"])),
        ("Clarify recall", _fmt_pct(m["clarify_recall"])),
        ("SQL validity", _fmt_pct(m["sql_validity_rate"])),
        ("SQL guard-block", _fmt_pct(m["sql_guard_block_rate"])),
        ("SQL path (llm/fallback)", f"{m['sql_llm_path']}/{m['sql_fallback_path']}"),
        (f"Attack block (n={m['attack_total']})", _fmt_pct(m["attack_block_rate"])),
        ("Off-topic block", _fmt_pct(m["offtopic_block_rate"])),
        (f"Hallucination rate (n={m['responded']})", _fmt_pct(m["hallucination_rate"])),
        (f"Price correctness (n={m['price_cases']})", _fmt_pct(m["price_correctness"])),
        ("Latency p50", f"{m['latency_p50_ms']:.1f} ms"),
        ("Latency p95", f"{m['latency_p95_ms']:.1f} ms"),
    ]


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
    ]
    lines += [f"| {name} | {val} |" for name, val in _rows(m)]
    lines += ["", "## Extraction accuracy by field", "", "| Field | Accuracy |", "|---|---|"]
    lines += [
        f"| {f} | {_fmt_pct(m['field_accuracy'][f])} |"
        for f in FIELDS if f in m["field_accuracy"]
    ]
    lines.append("")
    return "\n".join(lines)


def print_table(m: dict) -> None:
    print(f"\n=== Eval ({m['provider']}, {m['n_cases']} cases) ===")
    width = max(len(r[0]) for r in _rows(m))
    for name, val in _rows(m):
        print(f"  {name.ljust(width)} : {val}")
    print("  --- extraction by field ---")
    for f in FIELDS:
        if f in m["field_accuracy"]:
            print(f"  {f.ljust(width)} : {_fmt_pct(m['field_accuracy'][f])}")


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(prog="eval.run_eval")
    parser.add_argument("--provider", default=None, help="mock|openai|anthropic|ollama")
    parser.add_argument("--limit", type=int, default=None, help="only first N cases")
    parser.add_argument("--ids", default=None, help="comma-separated case ids")
    parser.add_argument("--ids-file", default=None, help="file with one id per line")
    parser.add_argument("--no-save", action="store_true", help="do not write results file")
    args = parser.parse_args(argv)

    ids: list[str] | None = None
    if args.ids:
        ids = [s.strip() for s in args.ids.split(",") if s.strip()]
    if args.ids_file:
        ids = (ids or []) + [
            ln.strip()
            for ln in Path(args.ids_file).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")
        ]

    m = run(args.provider, limit=args.limit, ids=ids, progress=True)
    print_table(m)
    if not args.no_save:
        out = Path(__file__).with_name(f"results_{m['provider']}.md")
        out.write_text(render_markdown(m), encoding="utf-8")
        print(f"\nWrote {out}")
    return m


if __name__ == "__main__":
    main()
