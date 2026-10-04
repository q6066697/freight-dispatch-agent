"""Command-line entry point.

    python -m app.cli "Нужно отвезти 12 тонн труб из Минска в Москву, тент, безнал"

Flags:
    --provider mock|openai|anthropic|ollama   override LLM_PROVIDER
    --json                                     print the full response as JSON
    --verbose                                  print extraction, SQL, guard verdict,
                                               row/option counts and the sql path
"""

from __future__ import annotations

import argparse
import json
import sys

from app.db import db_path
from app.graph import run_graph, to_response
from db.seed import build


def _print_verbose(final: dict) -> None:
    req = final.get("request") or {}
    attempts = final.get("sql_attempts") or []
    print("=== VERBOSE ===", file=sys.stderr)
    print("extracted (normalized):", file=sys.stderr)
    print(json.dumps(req, ensure_ascii=False, indent=2), file=sys.stderr)
    print(f"\nsql_path: {final.get('sql_path')}", file=sys.stderr)
    for a in attempts:
        verdict = "OK" if a.get("ok") else f"BLOCKED ({a.get('reason')})"
        print(f"  [{a.get('path')}] attempt {a.get('attempt')}: {verdict}", file=sys.stderr)
        if a.get("raw"):
            print(f"    SQL: {a['raw']}", file=sys.stderr)
    print(f"\nrows: {len(final.get('rows') or [])}  "
          f"options: {len(final.get('options') or [])}", file=sys.stderr)
    steps = ">".join(s["step"] for s in final.get("trace", []))
    print(f"steps: {steps}", file=sys.stderr)
    print("=== END VERBOSE ===\n", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli", description="Freight dispatcher")
    parser.add_argument("text", help="Free-text cargo request (Russian)")
    parser.add_argument("--provider", default=None, help="Override LLM provider")
    parser.add_argument("--json", action="store_true", help="Print full JSON response")
    parser.add_argument("--verbose", action="store_true", help="Print pipeline internals")
    args = parser.parse_args(argv)

    if not db_path().exists():
        print("Building synthetic database...", file=sys.stderr)
        build()

    final = run_graph(args.text, provider_name=args.provider)
    if args.verbose:
        _print_verbose(final)
    resp = to_response(final)

    if args.json:
        print(resp.model_dump_json(indent=2))
        return 0

    print(resp.reply)
    if resp.options:
        print("\n--- варианты (детали) ---")
        for i, opt in enumerate(resp.options[:3], start=1):
            print(
                f"{i}. {opt.carrier} | {opt.body_type} {opt.capacity_t} т | "
                f"{opt.price:.0f} {opt.currency} | ~{opt.eta_days} сут | "
                f"рейтинг {opt.rating}"
            )
    print(f"\n[status={resp.status}; steps={'>'.join(s.step for s in resp.trace)}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
