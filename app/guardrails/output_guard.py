"""Output guard: make sure the reply only names carriers and prices from state.

A real model invented carriers and prices on a no-options request (see
docs/case-hallucination.md). This guard parses the composed reply and flags:
  - any price (a number next to руб/RUB/₽ or after "цена/стоимость") that is not an
    option's total price;
  - any organization mention (quoted name or legal-form token) that does not match
    an option's carrier name.
On any violation the responder falls back to a deterministic grounded template.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Prices: a number (optionally space/nbsp grouped) that is clearly a money amount.
_PRICE_NEAR_CURRENCY = re.compile(
    r"(\d[\d  ]{2,}\d|\d{4,})\s*(?:руб|руб\.|рублей|rub|₽|br|бр)", re.I
)
_PRICE_AFTER_WORD = re.compile(
    r"(?:цен[аеуы]|стоимост\w*|за\s+рейс)\D{0,15}?(\d[\d  ]{2,}\d|\d{4,})", re.I
)

# Organization mentions: a quoted name, or a legal-form token followed by a name.
_QUOTED = re.compile(r"[«\"']([^«»\"']{2,48})[»\"']")
_LEGAL_FORM = re.compile(
    r"\b(?:ООО|ОДО|ЧТУП|УП|ЗАО|ОАО|ПАО|ИП|ФКУ|ФГУП|МУП|UAB|Sp\.?\s*z\s*o\.?\s*o\.?)\b"
    r"[\s«\"']*([A-Za-zА-Яа-яЁё][\w .«»\"'-]{1,48})?",
    re.I,
)


def _digits(s: str) -> int:
    return int(re.sub(r"[  ]", "", s))


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().replace("ё", "е")).strip(" .«»\"'")


@dataclass
class OutputScreen:
    ok: bool
    violations: list[str] = field(default_factory=list)


def check_reply(reply: str, options: list[dict[str, Any]]) -> OutputScreen:
    """Verify every carrier/price in `reply` is backed by `options`."""
    if not reply or not reply.strip():
        return OutputScreen(ok=True)

    violations: list[str] = []

    # Allowed prices: option totals, rounded to int (allow ±1 for formatting).
    allowed_prices = {round(float(o.get("price", 0))) for o in options}
    for m in list(_PRICE_NEAR_CURRENCY.finditer(reply)) + list(
        _PRICE_AFTER_WORD.finditer(reply)
    ):
        val = _digits(m.group(1))
        if val < 1000:
            continue
        if not any(abs(val - p) <= 1 for p in allowed_prices):
            violations.append(f"price not in options: {val}")

    # Allowed carriers: normalized full names.
    allowed_carriers = [_norm(o.get("carrier", "")) for o in options]

    def _known(name: str) -> bool:
        n = _norm(name)
        if not n:
            return True
        return any(n in c or c in n for c in allowed_carriers)

    mentions: list[str] = []
    mentions += [m.group(1) for m in _QUOTED.finditer(reply)]
    mentions += [m.group(0) for m in _LEGAL_FORM.finditer(reply)]
    for name in mentions:
        if not _known(name):
            violations.append(f"carrier not in options: {name.strip()}")

    # De-duplicate while preserving order.
    seen: set[str] = set()
    unique = [v for v in violations if not (v in seen or seen.add(v))]
    return OutputScreen(ok=not unique, violations=unique)
