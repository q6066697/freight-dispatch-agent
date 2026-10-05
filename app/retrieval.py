"""Trusted, parameterized candidate search + authoritative route distance (D18).

Unlike the LLM-generated query (which must pass `sql_guard`), the candidate query is
written by us and uses bound parameters, so it is safe by construction. It does NOT
join `routes`: route distance is looked up separately by `route_distance`, so a truck
is returned whether or not we serve its lane, and pricing decides `no_route`.
"""

from __future__ import annotations

from typing import Any

from app.db import readonly_connection

_SQL = """
SELECT t.id AS truck_id, t.plate, t.body_type, t.capacity_t, t.volume_m3,
       t.current_city, c.id AS carrier_id, c.name AS carrier, c.rating,
       c.payment_terms, r.rate_per_km, r.min_price, r.currency
FROM trucks t
JOIN carriers c ON c.id = t.carrier_id
JOIN rates r ON r.carrier_id = c.id AND r.body_type = t.body_type
WHERE t.status = 'free'
  AND t.body_type = ?
  AND t.capacity_t >= ?
  {payment_clause}
ORDER BY c.rating DESC, r.rate_per_km ASC
LIMIT 20
"""


def build_candidate_query(request: dict[str, Any]) -> tuple[str, list]:
    """Return (sql, params) for the canonical candidate search."""
    body_type = request.get("body_type") or "тент"
    weight = float(request.get("weight_t") or 0)
    payment = request.get("payment")

    params: list = [body_type, weight]
    payment_clause = ""
    if payment == "noncash":
        payment_clause = "AND c.payment_terms IN ('noncash','both')"
    elif payment == "cash":
        payment_clause = "AND c.payment_terms IN ('cash','both')"

    return _SQL.format(payment_clause=payment_clause), params


def run_candidates(request: dict[str, Any]) -> list[dict]:
    """Execute the parameterized candidate search read-only; return row dicts.

    Rows carry a route-derived `distance_km` (or None if the lane is unknown), so they
    satisfy the same contract as accepted LLM rows.
    """
    sql, params = build_candidate_query(request)
    distance = route_distance(request.get("origin"), request.get("destination"))
    conn = readonly_connection()
    try:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()
    for row in rows:
        row["distance_km"] = distance
    return rows


def route_distance(origin: Any, destination: Any) -> int | None:
    """Authoritative road distance for a lane, from `routes`. None if unknown."""
    if not origin or not destination:
        return None
    conn = readonly_connection()
    try:
        row = conn.execute(
            "SELECT distance_km FROM routes WHERE origin = ? AND destination = ?",
            (origin, destination),
        ).fetchone()
    finally:
        conn.close()
    return int(row["distance_km"]) if row else None
