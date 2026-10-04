"""Deterministic freight pricing. NO LLM is involved — money must be reproducible.

Formula (see DECISIONS.md D9):
    base       = rate_per_km * distance_km
    after_load = base * load_factor          # догруз (partial) < full truck
    total      = after_load * (1 + urgency% + body%)
    total      = max(total, min_price), rounded to the nearest 100

Every component is exposed in `PriceBreakdown` so a quote can be explained line by
line and asserted in unit tests.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

URGENCY_PCT = 0.25  # срочная / next-day delivery
BODY_SURCHARGE_PCT = {"реф": 0.08, "изотерм": 0.04, "тент": 0.0, "борт": 0.0}
PARTIAL_MIN_FACTOR = 0.4  # a догруз is never billed below 40% of a full truck
ROUND_TO = 100


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _round_to(x: float, step: int = ROUND_TO) -> float:
    return float(round(x / step) * step)


def load_factor(
    load_type: str,
    *,
    weight_t: float | None = None,
    capacity_t: float | None = None,
    volume_m3: float | None = None,
    truck_volume_m3: float | None = None,
) -> float:
    """Fraction of a full-truck price to charge.

    `full` → 1.0. `partial` (догруз) → the larger of weight-share and volume-share
    of the truck, clamped to [PARTIAL_MIN_FACTOR, 1.0]. Unknown shares default to
    the minimum factor.
    """
    if load_type != "partial":
        return 1.0
    share = 0.0
    if weight_t and capacity_t:
        share = max(share, weight_t / capacity_t)
    if volume_m3 and truck_volume_m3:
        share = max(share, volume_m3 / truck_volume_m3)
    if share <= 0:
        share = PARTIAL_MIN_FACTOR
    return _clamp(share, PARTIAL_MIN_FACTOR, 1.0)


@dataclass
class PriceBreakdown:
    distance_km: float
    rate_per_km: float
    base: float
    load_type: str
    load_factor: float
    after_load: float
    body_type: str
    body_surcharge_pct: float
    urgent: bool
    urgency_pct: float
    surcharge_amount: float
    subtotal: float
    min_price: float
    min_applied: bool
    total: float
    currency: str

    def as_dict(self) -> dict:
        return asdict(self)


def price_quote(
    *,
    distance_km: float,
    rate_per_km: float,
    min_price: float,
    body_type: str = "тент",
    urgent: bool = False,
    load_type: str = "full",
    weight_t: float | None = None,
    capacity_t: float | None = None,
    volume_m3: float | None = None,
    truck_volume_m3: float | None = None,
    currency: str = "RUB",
) -> PriceBreakdown:
    """Compute a fully itemized price for one carrier/truck option."""
    if distance_km < 0 or rate_per_km < 0 or min_price < 0:
        raise ValueError("distance_km, rate_per_km and min_price must be non-negative")

    base = rate_per_km * distance_km

    lf = load_factor(
        load_type,
        weight_t=weight_t,
        capacity_t=capacity_t,
        volume_m3=volume_m3,
        truck_volume_m3=truck_volume_m3,
    )
    after_load = base * lf

    body_pct = BODY_SURCHARGE_PCT.get(body_type, 0.0)
    urgency_pct = URGENCY_PCT if urgent else 0.0
    surcharge_mult = 1.0 + urgency_pct + body_pct
    surcharge_amount = after_load * (surcharge_mult - 1.0)

    raw_total = after_load * surcharge_mult
    min_applied = raw_total < min_price
    total = _round_to(max(raw_total, min_price))

    return PriceBreakdown(
        distance_km=float(distance_km),
        rate_per_km=float(rate_per_km),
        base=round(base, 2),
        load_type=load_type,
        load_factor=round(lf, 4),
        after_load=round(after_load, 2),
        body_type=body_type,
        body_surcharge_pct=body_pct,
        urgent=urgent,
        urgency_pct=urgency_pct,
        surcharge_amount=round(surcharge_amount, 2),
        subtotal=round(raw_total, 2),
        min_price=float(min_price),
        min_applied=min_applied,
        total=total,
        currency=currency,
    )
