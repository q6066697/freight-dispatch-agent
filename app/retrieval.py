"""Trusted, parameterized candidate search — the deterministic SQL fallback (D15).

Unlike the LLM-generated query (which must pass `sql_guard`), this query is written
by us and uses bound parameters, so it is safe by construction. It runs on the same
read-only connection. `sql_agent` uses it when the model fails to produce a working
query, or produces a valid query that returns no rows for a complete request.
"""

from __future__ import annotations

from typing import Any

from app.db import readonly_connection

_SQL = """
SELECT t.id AS truck_id, t.plate, t.body_type, t.capacity_t, t.volume_m3,
       t.current_city, c.id AS carrier_id, c.name AS carrier, c.rating,
       c.payment_terms, r.rate_per_km, r.min_price, r.currency, rt.distance_km
FROM trucks t
JOIN carriers c ON c.id = t.carrier_id
JOIN rates r ON r.carrier_id = c.id AND r.body_type = t.body_type
JOIN routes rt ON rt.origin = ? AND rt.destination = ?
WHERE t.status = 'free'
  AND t.body_type = ?
  AND t.capacity_t >= ?
  {payment_clause}
ORDER BY c.rating DESC, r.rate_per_km ASC
LIMIT 20
"""


def build_candidate_query(request: dict[str, Any]) -> tuple[str, list]:
    """Return (sql, params) for the canonical candidate search."""
    origin = request.get("origin") or ""
    destination = request.get("destination") or ""
    body_type = request.get("body_type") or "тент"
    weight = float(request.get("weight_t") or 0)
    payment = request.get("payment")

    params: list = [origin, destination, body_type, weight]
    payment_clause = ""
    if payment == "noncash":
        payment_clause = "AND c.payment_terms IN ('noncash','both')"
    elif payment == "cash":
        payment_clause = "AND c.payment_terms IN ('cash','both')"

    sql = _SQL.format(payment_clause=payment_clause)
    return sql, params


def run_candidates(request: dict[str, Any]) -> list[dict]:
    """Execute the parameterized candidate search read-only; return row dicts."""
    sql, params = build_candidate_query(request)
    conn = readonly_connection()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()
