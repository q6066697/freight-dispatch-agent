"""Deterministic normalization of extracted request fields (D15).

A real (small) model echoes inflected, mis-cased city names ("минска", "москву")
and inconsistent enum spellings ("рефрижератор", "нал"). This module maps them to
the canonical forms the database and schema expect, independently of which LLM
produced them. It is applied in the extractor node, after the provider returns.
"""

from __future__ import annotations

import re
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


# Dispatcher-slang body-type lexicon (D21), used to backfill when the model leaves
# body_type empty. Order matters: specific bodies before the generic tilt.
_BODY_DETECT = [
    ("реф", re.compile(r"рефриж|\bреф\b|\bрефы?\b|рефка|рефрижератор")),
    ("изотерм", re.compile(r"изотерм")),
    ("борт", re.compile(r"\bборт|бортов|открыт\w*\s+платформ")),
    ("тент", re.compile(r"тент|еврофур|\bфур|штор|тентов")),
]


def detect_body_type(text: Any) -> str | None:
    """Infer a canonical body type from free text (slang-aware), else None."""
    if not text or not isinstance(text, str):
        return None
    t = _norm(text)
    for name, pat in _BODY_DETECT:
        if pat.search(t):
            return name
    return None


_NUM_RE = re.compile(r"-?\d+(?:[.,]\d+)?")
_TRUE_WORDS = {"true", "1", "yes", "y", "да", "срочно", "urgent"}


def _coerce_number(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = _NUM_RE.search(v)
        return float(m.group(0).replace(",", ".")) if m else None
    return None


def _coerce_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in _TRUE_WORDS
    return False


def coerce_types(raw: dict[str, Any]) -> dict[str, Any]:
    """Deterministically coerce fields so ExtractedRequest can always be built.

    Numbers are parsed out of strings, booleans from да/нет/yes/1, and enum fields are
    canonicalized (invalid values become None). This never raises — it is the
    last-resort repair in the extractor node (D22).
    """
    d = normalize_request(raw)
    if "weight_t" in d:
        d["weight_t"] = _coerce_number(d.get("weight_t"))
    if "volume_m3" in d:
        d["volume_m3"] = _coerce_number(d.get("volume_m3"))
    if "urgent" in d:
        d["urgent"] = _coerce_bool(d.get("urgent"))
    if d.get("payment") not in ("cash", "noncash", None):
        d["payment"] = canonical_payment(d.get("payment"))
    if d.get("load_type") not in ("full", "partial", None):
        d["load_type"] = canonical_load_type(d.get("load_type"))
    return d


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
