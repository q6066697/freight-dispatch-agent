"""Contract + semantic filter for rows returned by the model's SQL (D18).

The SQL guard proves a query is *safe*; it cannot prove it is *correct*. A real model
passed the guard but returned rows that were unusable (no `distance_km` because it
never joined `routes`, confused `payment` with `currency`, matched `body_type LIKE
'%трубы%'`). This module rejects such rows so the SQL agent can fall back
deterministically instead of corrupting pricing.
"""

from __future__ import annotations

from typing import Any

# Columns pricing / responder rely on. `distance_km` is required as a proxy that the
# query actually joined `routes`; its *value* is not trusted (pricing re-derives it).
REQUIRED_COLUMNS = (
    "carrier",
    "plate",
    "body_type",
    "capacity_t",
    "volume_m3",
    "current_city",
    "rating",
    "rate_per_km",
    "min_price",
    "payment_terms",
    "distance_km",
)

_NUMERIC_COLUMNS = (
    "capacity_t",
    "volume_m3",
    "rate_per_km",
    "min_price",
    "rating",
    "distance_km",
)


def validate_rows(rows: list[dict[str, Any]]) -> str | None:
    """Return a failure reason, or None if every row satisfies the contract.

    Reasons: 'missing_columns' | 'invalid_values'. (Empty input is the caller's
    concern — see sql_agent, which reports 'zero_rows'.)
    """
    for row in rows:
        if any(col not in row for col in REQUIRED_COLUMNS):
            return "missing_columns"
        for col in _NUMERIC_COLUMNS:
            try:
                float(row[col])
            except (TypeError, ValueError):
                return "invalid_values"
    return None


def semantic_filter(
    rows: list[dict[str, Any]], request: dict[str, Any]
) -> list[dict[str, Any]]:
    """Keep only rows that actually satisfy the request (body/capacity/payment)."""
    body = request.get("body_type")
    weight = float(request.get("weight_t") or 0)
    payment = request.get("payment")

    out: list[dict[str, Any]] = []
    for row in rows:
        if body and str(row.get("body_type")) != body:
            continue
        try:
            if float(row.get("capacity_t")) < weight:
                continue
        except (TypeError, ValueError):
            continue
        terms = row.get("payment_terms")
        if payment == "noncash" and terms not in ("noncash", "both"):
            continue
        if payment == "cash" and terms not in ("cash", "both"):
            continue
        out.append(row)
    return out
