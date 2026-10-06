"""Evaluation harness (crash-isolated, append-only, resumable — D20).

Each case is run independently; an exception becomes a record with status="error"
(the run continues). Every per-case record is streamed to
eval/runs/<provider>_<timestamp>.jsonl, and the final table is aggregated from that
file, so an interrupted overnight run can be resumed with --resume.

Metrics: extraction field accuracy, clarify precision/recall, SQL validity + guard
block, sql_path / fallback_reason distributions, attack & off-topic block rate,
hallucination rate, price correctness, error rate, latency p50/p95.

Examples:
  python -m eval.run_eval
  python -m eval.run_eval --provider ollama --ids-file eval/subset_cpu.txt
  python -m eval.run_eval --provider ollama --resume eval/runs/ollama_20261005_0130.jsonl
"""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from app.graph import build_graph, to_response
from app.guardrails.output_guard import check_reply
from app.llm import get_provider

DATASET = Path(__file__).with_name("dataset.jsonl")
RUNS_DIR = Path(__file__).with_name("runs")

FIELDS = [
    "origin", "destination", "weight_t", "volume_m3",
    "body_type", "payment", "urgent", "load_type",
]
EXTRACTION_CATEGORIES = {"normal", "slang", "incomplete", "edge", "no_route"}
RESPONDED_STATUSES = {"ok", "no_options", "no_route"}


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


def evaluate_case(graph, case: dict) -> dict:
    """Run one case and return a flat result record. Never raises."""
    exp = case["expected"]
    rec: dict = {
        "id": case["id"],
        "category": case["category"],
        "expected_status": exp["status"],
    }
    t0 = time.perf_counter()
    try:
        final = graph.invoke({"text": case["text"]})
        resp = to_response(final)
        rec["latency_ms"] = (time.perf_counter() - t0) * 1000
        rec["status"] = resp.status
        rec["error"] = None
        rec["sql_path"] = final.get("sql_path")
        rec["fallback_reason"] = final.get("fallback_reason")
        # Persist detail for offline error analysis without re-running (D24).
        rec["extracted"] = final.get("request")
        rec["reply"] = resp.reply
        rec["sql_attempts"] = [
            {"path": a.get("path"), "ok": a.get("ok"), "reason": a.get("reason"),
             "raw": a.get("raw")}
            for a in (final.get("sql_attempts") or [])
        ]

        fields: dict[str, bool] = {}
        gold = exp.get("fields", {})
        if case["category"] in EXTRACTION_CATEGORIES and gold:
            for f, gold_v in gold.items():
                if f in FIELDS:
                    got_v = getattr(resp.request, f, None) if resp.request else None
                    fields[f] = _norm(got_v) == _norm(gold_v)
        rec["fields"] = fields

        if resp.status in RESPONDED_STATUSES:
            opts = [{"carrier": o.carrier, "price": o.price} for o in resp.options]
            rec["responded"] = True
            rec["hallucinated"] = not check_reply(resp.reply, opts).ok
        else:
            rec["responded"] = False
            rec["hallucinated"] = False

        if exp.get("price_rub") is not None:
            rec["price_applicable"] = True
            rec["price_ok"] = bool(
                resp.options and abs(resp.options[0].price - exp["price_rub"]) < 1.0
            )
        else:
            rec["price_applicable"] = False
            rec["price_ok"] = False
    except Exception as e:  # noqa: BLE001 - one bad case must not kill the run
        rec["latency_ms"] = (time.perf_counter() - t0) * 1000
        rec["status"] = "error"
        rec["error"] = type(e).__name__
        rec["sql_path"] = None
        rec["fallback_reason"] = None
        rec["extracted"] = None
        rec["reply"] = None
        rec["sql_attempts"] = []
        rec["fields"] = {}
        rec["responded"] = False
        rec["hallucinated"] = False
        rec["price_applicable"] = False
        rec["price_ok"] = False
    return rec


def _read_records(path: Path) -> list[dict]:
    if not path or not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def run(
    provider_name: str | None = None,
    *,
    limit: int | None = None,
    ids: list[str] | None = None,
    progress: bool = False,
    out_path: str | Path | None = None,
    resume: str | Path | None = None,
) -> dict:
    effective = provider_name or "mock"
    provider = get_provider(effective)
    graph = build_graph(provider)

    cases = load_cases()
    if ids:
        wanted = set(ids)
        cases = [c for c in cases if c["id"] in wanted]
    if limit:
        cases = cases[:limit]

    # Resume: reuse the file, keep its records, skip ids already done.
    target = Path(resume) if resume else (Path(out_path) if out_path else None)
    records = _read_records(Path(resume)) if resume else []
    done = {r["id"] for r in records}
    if target:
        target.parent.mkdir(parents=True, exist_ok=True)

    pending = [c for c in cases if c["id"] not in done]
    for idx, case in enumerate(pending, start=1):
        rec = evaluate_case(graph, case)
        records.append(rec)
        if target:
            with target.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if progress:
            tag = rec["error"] or rec["status"]
            print(f"[{idx}/{len(pending)}] {case['id']:<14} {tag:<14} "
                  f"{rec['latency_ms'] / 1000:6.1f}s", flush=True)

    m = aggregate(records)
    m["provider"] = provider.name
    if target:
        m["run_file"] = str(target)
    return m


def aggregate(records: list[dict]) -> dict:
    field_hits = {f: [0, 0] for f in FIELDS}
    clarify = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    attack_total = attack_blocked = 0
    offtopic_total = offtopic_blocked = 0
    price_total = price_ok = 0
    responded = hallucinated = status_hits = errors = 0
    sql_paths: Counter = Counter()
    fallback_reasons: Counter = Counter()
    latencies: list[float] = []

    for r in records:
        latencies.append(r.get("latency_ms", 0.0))
        status_hits += r.get("status") == r.get("expected_status")
        errors += r.get("status") == "error"

        for f, ok in (r.get("fields") or {}).items():
            if f in field_hits:
                field_hits[f][1] += 1
                field_hits[f][0] += bool(ok)

        if r.get("category") in EXTRACTION_CATEGORIES:
            want = r.get("expected_status") == "clarify"
            pred = r.get("status") == "clarify"
            key = ("tp" if pred else "fn") if want else ("fp" if pred else "tn")
            clarify[key] += 1

        if r.get("category") == "attack":
            attack_total += 1
            attack_blocked += r.get("status") == "refused"
        if r.get("category") == "offtopic":
            offtopic_total += 1
            offtopic_blocked += r.get("status") == "refused"

        if r.get("sql_path"):
            sql_paths[r["sql_path"]] += 1
        if r.get("fallback_reason"):
            fallback_reasons[r["fallback_reason"]] += 1

        if r.get("responded"):
            responded += 1
            hallucinated += bool(r.get("hallucinated"))

        if r.get("price_applicable"):
            price_total += 1
            price_ok += bool(r.get("price_ok"))

    prec = _ratio(clarify["tp"], clarify["tp"] + clarify["fp"])
    rec_ = _ratio(clarify["tp"], clarify["tp"] + clarify["fn"])
    n = len(records)
    return {
        "provider": "?",
        "n_cases": n,
        "status_accuracy": _ratio(status_hits, n),
        "error_rate": _ratio(errors, n),
        "errors": errors,
        "field_accuracy": {f: _ratio(h, a) for f, (h, a) in field_hits.items() if a},
        "field_accuracy_overall": _ratio(
            sum(h for h, _ in field_hits.values()),
            sum(a for _, a in field_hits.values()),
        ),
        "clarify_precision": prec if prec is not None else 1.0,
        "clarify_recall": rec_ if rec_ is not None else 1.0,
        "attack_block_rate": _ratio(attack_blocked, attack_total),
        "attack_total": attack_total,
        "offtopic_block_rate": _ratio(offtopic_blocked, offtopic_total),
        "hallucination_rate": _ratio(hallucinated, responded),
        "responded": responded,
        "sql_path_dist": dict(sql_paths),
        "fallback_reason_dist": dict(fallback_reasons),
        "price_cases": price_total,
        "price_correctness": _ratio(price_ok, price_total),
        "latency_p50_ms": _percentile(latencies, 50),
        "latency_p95_ms": _percentile(latencies, 95),
    }


def _fmt_pct(x) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def _dist(d: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in sorted(d.items())) if d else "—"


def _rows(m: dict) -> list[tuple[str, str]]:
    return [
        ("Status accuracy", _fmt_pct(m["status_accuracy"])),
        (f"Error rate (n={m['errors']})", _fmt_pct(m["error_rate"])),
        ("Extraction (overall)", _fmt_pct(m["field_accuracy_overall"])),
        ("Clarify precision", _fmt_pct(m["clarify_precision"])),
        ("Clarify recall", _fmt_pct(m["clarify_recall"])),
        ("SQL path", _dist(m["sql_path_dist"])),
        ("Fallback reasons", _dist(m["fallback_reason_dist"])),
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
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
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
    parser.add_argument("--resume", default=None, help="append to / resume a run jsonl")
    parser.add_argument("--no-save", action="store_true", help="do not write files")
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

    provider = (args.provider or "mock").lower()
    out_path = None
    if not args.no_save and not args.resume:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = RUNS_DIR / f"{provider}_{ts}.jsonl"

    m = run(args.provider, limit=args.limit, ids=ids, progress=True,
            out_path=out_path, resume=args.resume)
    print_table(m)
    if not args.no_save:
        results = Path(__file__).with_name(f"results_{m['provider']}.md")
        results.write_text(render_markdown(m), encoding="utf-8")
        print(f"\nWrote {results}")
        if m.get("run_file"):
            print(f"Per-case records: {m['run_file']}")
    return m


if __name__ == "__main__":
    main()
