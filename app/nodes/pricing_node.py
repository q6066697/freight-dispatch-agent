"""pricing node: deterministically price each candidate truck (no LLM).

Produces at most one option per carrier (the cheapest), sorted by price, so the
responder can offer genuinely different carriers rather than three trucks from one.
"""

from __future__ import annotations

from app.llm.base import LLMProvider
from app.llm.mock import estimate_eta_days
from app.pricing import price_quote
from app.schemas import CarrierOption
from app.state import DispatchState


def pricing_node(state: DispatchState, provider: LLMProvider) -> dict:
    request = state.get("request") or {}
    rows = state.get("rows") or []

    options: list[dict] = []
    for row in rows:
        distance = float(row["distance_km"])
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
            distance_km=distance,
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
        "detail": {"candidates": len(options), "options": len(deduped)},
    }
    return {"priced": True, "options": deduped, "trace": [step]}
