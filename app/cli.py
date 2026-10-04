"""Command-line entry point.

    python -m app.cli "Нужно отвезти 12 тонн труб из Минска в Москву, тент, безнал"

Flags:
    --provider mock|openai|anthropic|ollama   override LLM_PROVIDER
    --json                                     print the full response as JSON
"""

from __future__ import annotations

import argparse
import sys

from app.db import db_path
from app.graph import dispatch
from db.seed import build


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli", description="Freight dispatcher")
    parser.add_argument("text", help="Free-text cargo request (Russian)")
    parser.add_argument("--provider", default=None, help="Override LLM provider")
    parser.add_argument("--json", action="store_true", help="Print full JSON response")
    args = parser.parse_args(argv)

    if not db_path().exists():
        print("Building synthetic database...", file=sys.stderr)
        build()

    resp = dispatch(args.text, provider_name=args.provider)

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
