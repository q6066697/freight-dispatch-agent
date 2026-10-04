"""Deterministic, offline mock provider.

Implements the task methods with rules so the ENTIRE graph, tests and eval run with
no API key and no network. The extractor is a small rule-based Russian NLU tuned for
dispatcher phrasing (еврофура, тентовка, догруз, inflected city names).
"""

from __future__ import annotations

import math
import re

from app.guardrails.input_guard import screen_input
from app.llm.base import LLMProvider
from app.normalize import CITY_STEMS as _CITY_STEMS
from app.reply_templates import grounded_reply

_BODY_PATTERNS = [
    ("реф", re.compile(r"рефриж|\bреф\b|\bрефы?\b|рефка|рефрижератор")),
    ("изотерм", re.compile(r"изотерм")),
    ("борт", re.compile(r"\bборт|бортов|открыт\w*\s+платформ")),
    ("тент", re.compile(r"тент|еврофур|\bфур|штор|тентов")),
]

_WEIGHT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:тонн[а-я]*|тн|т)(?![а-яa-z])", re.I)
_VOLUME_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:куб\w*|м3|м³|m3|кубов)(?![а-я])", re.I)

_PAY_NONCASH = re.compile(r"безнал|б/н|перечислен|на\s+счет|по\s+счет|с\s+ндс|\bндс\b")
_PAY_CASH = re.compile(r"налич|наличк|за\s+нал|\bнал\b")

_URGENT_RE = re.compile(r"срочн|сегодня|завтра|asap|горит|как\s+можно\s+быстрее")

_PARTIAL_RE = re.compile(r"догруз|дозагруз|сборн|частичн")
_FULL_RE = re.compile(r"отдельн\w*\s+машин|целую?\s+машин|полн\w*\s+загруз|эксклюзив|под\s+завязку")

_DATE_RE = re.compile(
    r"(?:в\s+)?(понедельник|вторник|сред[ау]|четверг|пятниц[ау]|суббот[ау]|"
    r"воскресень\w*|сегодня|послезавтра|завтра)|(\d{1,2}[.\s]\d{1,2}(?:\.\d{2,4})?)",
    re.I,
)

_CARGO_RE = re.compile(
    r"(?:тонн[а-я]*|куб\w*|м3)\s+([а-яё]+)|"
    r"(?:отвезти|перевезти|везти|доставить|перевозк[аиуе]|груз[:\s])\s+([а-яё]+)",
    re.I,
)


def _norm(text: str) -> str:
    return text.lower().replace("ё", "е")


def _word_to_city(word: str) -> str | None:
    w = _norm(word)
    for city, stems in _CITY_STEMS.items():
        for stem in stems:
            if stem.replace("ё", "е") in w:
                return city
    return None


def _ordered_cities(text: str) -> list[str]:
    norm = _norm(text)
    hits: list[tuple[int, str]] = []
    for city, stems in _CITY_STEMS.items():
        pos = min(
            (norm.find(s.replace("ё", "е")) for s in stems if s.replace("ё", "е") in norm),
            default=-1,
        )
        if pos >= 0:
            hits.append((pos, city))
    hits.sort()
    # de-dup keeping order
    seen: set[str] = set()
    out: list[str] = []
    for _, c in hits:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _extract_cities(text: str) -> tuple[str | None, str | None]:
    origin = destination = None
    for m in re.finditer(r"\b(из|от)\s+([а-яё\-]+)", text, re.I):
        c = _word_to_city(m.group(2))
        if c:
            origin = c
            break
    for m in re.finditer(r"\b(в|во|до|на)\s+([а-яё\-]+)", text, re.I):
        c = _word_to_city(m.group(2))
        if c and c != origin:
            destination = c
            break
    # Fill gaps from positional order of all mentioned cities.
    if origin is None or destination is None:
        ordered = [c for c in _ordered_cities(text) if c not in (origin, destination)]
        it = iter(ordered)
        if origin is None:
            origin = next(it, None)
        if destination is None:
            destination = next((c for c in it if c != origin), None)
    return origin, destination


def _to_float(s: str) -> float:
    return float(s.replace(",", "."))


class MockProvider(LLMProvider):
    name = "mock"

    def classify_attack(self, text: str) -> dict:
        res = screen_input(text)
        return {
            "is_attack": res.is_attack,
            "category": res.category or "none",
            "reason": res.reason or "",
        }

    def extract_request(self, text: str) -> dict:
        norm = _norm(text)
        origin, destination = _extract_cities(text)

        weight = None
        if m := _WEIGHT_RE.search(text):
            weight = _to_float(m.group(1))
        volume = None
        if m := _VOLUME_RE.search(text):
            volume = _to_float(m.group(1))

        body_type = None
        for name, pat in _BODY_PATTERNS:
            if pat.search(norm):
                body_type = name
                break

        payment = None
        if _PAY_NONCASH.search(norm):
            payment = "noncash"
        elif _PAY_CASH.search(norm):
            payment = "cash"

        urgent = bool(_URGENT_RE.search(norm))

        load_type = None
        if _PARTIAL_RE.search(norm):
            load_type = "partial"
        elif _FULL_RE.search(norm):
            load_type = "full"

        date = None
        if m := _DATE_RE.search(text):
            date = (m.group(1) or m.group(2) or "").strip() or None

        cargo_type = None
        if m := _CARGO_RE.search(text):
            cargo_type = (m.group(1) or m.group(2) or "").strip() or None
            if cargo_type and _word_to_city(cargo_type):
                cargo_type = None  # a city name is not the cargo

        return {
            "origin": origin,
            "destination": destination,
            "cargo_type": cargo_type,
            "weight_t": weight,
            "volume_m3": volume,
            "body_type": body_type,
            "date": date,
            "payment": payment,
            "urgent": urgent,
            "load_type": load_type,
        }

    def generate_sql(self, request: dict, error: str | None = None) -> str:
        origin = (request.get("origin") or "").replace("'", "")
        destination = (request.get("destination") or "").replace("'", "")
        body_type = (request.get("body_type") or "тент").replace("'", "")
        weight = request.get("weight_t") or 0
        payment = request.get("payment")

        where = [
            "t.status = 'free'",
            f"t.body_type = '{body_type}'",
            f"t.capacity_t >= {float(weight)}",
        ]
        if payment == "noncash":
            where.append("c.payment_terms IN ('noncash','both')")
        elif payment == "cash":
            where.append("c.payment_terms IN ('cash','both')")

        sql = (
            "SELECT t.id AS truck_id, t.plate, t.body_type, t.capacity_t, "
            "t.volume_m3, t.current_city, c.id AS carrier_id, c.name AS carrier, "
            "c.rating, c.payment_terms, r.rate_per_km, r.min_price, r.currency, "
            "rt.distance_km "
            "FROM trucks t "
            "JOIN carriers c ON c.id = t.carrier_id "
            "JOIN rates r ON r.carrier_id = c.id AND r.body_type = t.body_type "
            f"JOIN routes rt ON rt.origin = '{origin}' AND rt.destination = '{destination}' "
            "WHERE " + " AND ".join(where) + " "
            "ORDER BY c.rating DESC, r.rate_per_km ASC "
            "LIMIT 20"
        )
        return sql

    def compose_reply(self, request: dict, options: list[dict]) -> str:
        # The mock is already deterministic and grounded; reuse the shared template.
        return grounded_reply(request, options)


def estimate_eta_days(distance_km: float) -> int:
    """Rough delivery estimate at ~650 km/day, at least one day."""
    return max(1, math.ceil(distance_km / 650))
