"""Deterministic pricing unit tests."""

import pytest

from app.pricing import (
    BODY_SURCHARGE_PCT,
    PARTIAL_MIN_FACTOR,
    URGENCY_PCT,
    load_factor,
    price_quote,
)


def test_base_price_simple():
    q = price_quote(distance_km=700, rate_per_km=55, min_price=15000)
    # 700*55 = 38500, no surcharge, above min, rounds to 38500
    assert q.base == 38500
    assert q.total == 38500
    assert not q.min_applied


def test_min_price_applied_for_short_trip():
    q = price_quote(distance_km=100, rate_per_km=50, min_price=15000)
    # 100*50 = 5000 < 15000 -> min applies
    assert q.min_applied
    assert q.total == 15000


def test_urgency_surcharge():
    base = price_quote(distance_km=700, rate_per_km=55, min_price=0)
    urgent = price_quote(distance_km=700, rate_per_km=55, min_price=0, urgent=True)
    expected = round((700 * 55) * (1 + URGENCY_PCT) / 100) * 100
    assert urgent.total == expected
    assert urgent.total > base.total
    assert urgent.urgency_pct == URGENCY_PCT


def test_body_surcharge_reefer():
    q = price_quote(distance_km=700, rate_per_km=78, min_price=0, body_type="реф")
    assert q.body_surcharge_pct == BODY_SURCHARGE_PCT["реф"]
    expected = round((700 * 78) * (1 + BODY_SURCHARGE_PCT["реф"]) / 100) * 100
    assert q.total == expected


def test_tent_has_no_body_surcharge():
    q = price_quote(distance_km=500, rate_per_km=55, min_price=0, body_type="тент")
    assert q.body_surcharge_pct == 0.0
    assert q.total == round((500 * 55) / 100) * 100


def test_combined_urgency_and_body_are_additive():
    q = price_quote(
        distance_km=600, rate_per_km=66, min_price=0, body_type="изотерм", urgent=True
    )
    mult = 1 + URGENCY_PCT + BODY_SURCHARGE_PCT["изотерм"]
    assert q.total == round((600 * 66) * mult / 100) * 100


def test_partial_load_cheaper_than_full():
    full = price_quote(
        distance_km=700, rate_per_km=55, min_price=0, load_type="full"
    )
    partial = price_quote(
        distance_km=700,
        rate_per_km=55,
        min_price=0,
        load_type="partial",
        weight_t=5,
        capacity_t=20,
        volume_m3=20,
        truck_volume_m3=86,
    )
    assert partial.total < full.total
    # weight share 0.25, volume share ~0.23 -> below floor -> clamps to 0.4
    assert partial.load_factor == PARTIAL_MIN_FACTOR


def test_partial_load_uses_larger_share():
    q = price_quote(
        distance_km=700,
        rate_per_km=55,
        min_price=0,
        load_type="partial",
        weight_t=14,
        capacity_t=20,  # weight share 0.7
        volume_m3=40,
        truck_volume_m3=86,  # volume share ~0.465
    )
    assert q.load_factor == pytest.approx(0.7, abs=1e-6)


def test_load_factor_full_is_one():
    assert load_factor("full") == 1.0


def test_load_factor_partial_unknown_defaults_to_floor():
    assert load_factor("partial") == PARTIAL_MIN_FACTOR


def test_negative_inputs_rejected():
    with pytest.raises(ValueError):
        price_quote(distance_km=-1, rate_per_km=55, min_price=0)


def test_determinism():
    kwargs = dict(distance_km=718, rate_per_km=61.5, min_price=15000, urgent=True,
                  body_type="реф")
    assert price_quote(**kwargs).total == price_quote(**kwargs).total
