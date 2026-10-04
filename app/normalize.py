"""Deterministic normalization of extracted request fields (D15).

A real (small) model echoes inflected, mis-cased city names ("минска", "москву")
and inconsistent enum spellings ("рефрижератор", "нал"). This module maps them to
the canonical forms the database and schema expect, independently of which LLM
produced them. It is applied in the extractor node, after the provider returns.
"""

from __future__ import annotations

from typing import Any

# canonical city -> lowercase stems (ё normalized to е), handling RU case inflection.
CITY_STEMS: dict[str, list[str]] = {
    "Минск": ["минск"],
    "Брест": ["брест"],
    "Гомель": ["гомел"],
    "Витебск": ["витебск"],
    "Могилёв": ["могил"],
    "Гродно": ["гродн"],
    "Москва": ["москв"],
    "Санкт-Петербург": ["санкт-петербург", "петербург", "питер", "спб"],
    "Смоленск": ["смоленск"],
    "Брянск": ["брянск"],
    "Калининград": ["калининград"],
    "Вильнюс": ["вильн"],
    "Каунас": ["каунас"],
    "Варшава": ["варшав"],
    "Гданьск": ["гданьск", "гдан"],
    "Лодзь": ["лодз"],
}


def _norm(text: str) -> str:
    return text.lower().replace("ё", "е").strip()


def canonical_city(value: Any) -> str | None:
    """Map a raw city string (any case/inflection) to a canonical name, else None."""
    if not value or not isinstance(value, str):
        return None
    w = _norm(value)
    for city, stems in CITY_STEMS.items():
        for stem in stems:
            if stem.replace("ё", "е") in w:
                return city
    return None


def canonical_body_type(value: Any) -> str | None:
    if not value or not isinstance(value, str):
        return None
    v = _norm(value)
    if "реф" in v:
        return "реф"
    if "изотерм" in v:
        return "изотерм"
    if "борт" in v:
        return "борт"
    if any(k in v for k in ("тент", "штор", "фур", "euro", "еврофур", "tent")):
        return "тент"
    return None


def canonical_payment(value: Any) -> str | None:
    if not value or not isinstance(value, str):
        return None
    v = _norm(value)
    if "безнал" in v or "noncash" in v or "card" in v or "ндс" in v or "перечисл" in v:
        return "noncash"
    if "нал" in v or "cash" in v:
        return "cash"
    return None


def canonical_load_type(value: Any) -> str | None:
    if not value or not isinstance(value, str):
        return None
    v = _norm(value)
    if "part" in v or "догруз" in v or "сборн" in v or "частич" in v:
        return "partial"
    if "full" in v or "полн" in v or "цел" in v or "отдельн" in v:
        return "full"
    return None


def normalize_request(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the extractor output with canonicalized fields."""
    data = dict(raw or {})

    if "origin" in data:
        data["origin"] = canonical_city(data.get("origin")) or None
    if "destination" in data:
        data["destination"] = canonical_city(data.get("destination")) or None

    if data.get("body_type") is not None:
        data["body_type"] = canonical_body_type(data.get("body_type"))
    if data.get("payment") is not None:
        data["payment"] = canonical_payment(data.get("payment"))
    if data.get("load_type") is not None:
        data["load_type"] = canonical_load_type(data.get("load_type"))

    return data
