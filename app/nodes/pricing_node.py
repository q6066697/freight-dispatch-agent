"""pricing node: deterministically price each candidate truck (no LLM).

Distance is NOT taken from the SQL rows — it is looked up authoritatively from
`routes` by normalized origin/destination (D18). If the lane is unknown the request
is `no_route`. Otherwise each truck is priced and the cheapest option per carrier is
kept, sorted by price.
"""

from __future__ import annotations

from app.llm.base import LLMProvider
from app.llm.mock import estimate_eta_days
from app.pricing import price_quote
from app.retrieval import route_distance
from app.schemas import CarrierOption
from app.state import DispatchState


def pricing_node(state: DispatchState, provider: LLMProvider) -> dict:
    request = state.get("request") or {}
    rows = state.get("rows") or []

    distance = route_distance(request.get("origin"), request.get("destination"))
    if distance is None:
        step = {"step": "pricing", "status": "no_route",
                "detail": {"reason": "route not in routes table"}}
        return {"priced": True, "options": [], "route_missing": True, "trace": [step]}

    options: list[dict] = []
    for row in rows:
        quote = price_quote(
            distance_km=distance,
            rate_per_km=float(row["rate_per_km"]),
            min_price=float(row["min_price"]),
            body_type=row["body_type"],
            urgent=bool(request.get("urgent")),
            load_type=request.get("load_type") or "full",
            weight_t=request.get("weight_t"),
            capacity_t=float(row["capacity_t"]),
            volume_m3=request.get("volume_m3"),
            truck_volume_m3=float(row["volume_m3"]),
            currency=row.get("currency", "RUB"),
        )
        option = CarrierOption(
            carrier=row["carrier"],
            truck_plate=row["plate"],
            body_type=row["body_type"],
            capacity_t=float(row["capacity_t"]),
            current_city=row["current_city"],
            rating=float(row["rating"]),
            distance_km=float(distance),
            eta_days=estimate_eta_days(distance),
            price=quote.total,
            currency=quote.currency,
            price_breakdown=quote.as_dict(),
        )
        options.append(option.model_dump())

    # Keep the cheapest option per carrier, then sort by price.
    best_by_carrier: dict[str, dict] = {}
    for opt in options:
        cur = best_by_carrier.get(opt["carrier"])
        if cur is None or opt["price"] < cur["price"]:
            best_by_carrier[opt["carrier"]] = opt
    deduped = sorted(best_by_carrier.values(), key=lambda o: (o["price"], -o["rating"]))

    step = {
        "step": "pricing",
        "status": "ok",
        "detail": {"candidates": len(options), "options": len(deduped),
                   "distance_km": distance},
    }
    return {"priced": True, "options": deduped, "route_missing": False,
            "trace": [step]}
