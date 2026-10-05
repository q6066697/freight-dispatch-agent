"""Unit tests for the LLM-SQL result contract and semantic filter (D18)."""

from app.sql_contract import semantic_filter, validate_rows

GOOD_ROW = {
    "carrier": "ООО «БелТрансЛогистик»", "plate": "AB1234-7", "body_type": "тент",
    "capacity_t": 20.0, "volume_m3": 86.0, "current_city": "Минск", "rating": 4.5,
    "rate_per_km": 55.0, "min_price": 15000.0, "payment_terms": "both",
    "distance_km": 718,
}


def test_valid_rows_pass():
    assert validate_rows([GOOD_ROW]) is None


def test_missing_distance_km_is_missing_columns():
    row = {k: v for k, v in GOOD_ROW.items() if k != "distance_km"}
    assert validate_rows([row]) == "missing_columns"


def test_missing_rate_is_missing_columns():
    row = {k: v for k, v in GOOD_ROW.items() if k != "rate_per_km"}
    assert validate_rows([row]) == "missing_columns"


def test_non_numeric_value_is_invalid_values():
    row = dict(GOOD_ROW, rate_per_km="noncash")  # model confused rate with payment
    assert validate_rows([row]) == "invalid_values"


def test_semantic_filter_keeps_matching():
    req = {"body_type": "тент", "weight_t": 10.0, "payment": "noncash"}
    assert semantic_filter([GOOD_ROW], req) == [GOOD_ROW]


def test_semantic_filter_drops_wrong_body():
    req = {"body_type": "реф", "weight_t": 10.0, "payment": "noncash"}
    assert semantic_filter([GOOD_ROW], req) == []


def test_semantic_filter_drops_insufficient_capacity():
    req = {"body_type": "тент", "weight_t": 25.0, "payment": "noncash"}
    assert semantic_filter([GOOD_ROW], req) == []


def test_semantic_filter_drops_incompatible_payment():
    cash_only = dict(GOOD_ROW, payment_terms="cash")
    req = {"body_type": "тент", "weight_t": 10.0, "payment": "noncash"}
    assert semantic_filter([cash_only], req) == []
