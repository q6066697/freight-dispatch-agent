"""City / field normalization tests (D15)."""

import pytest

from app.normalize import (
    canonical_body_type,
    canonical_city,
    canonical_payment,
    detect_body_type,
    normalize_request,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("минска", "Минск"),
        ("Минск", "Минск"),
        ("МОСКВУ", "Москва"),
        ("москве", "Москва"),
        ("в Санкт-Петербург", "Санкт-Петербург"),
        ("питер", "Санкт-Петербург"),
        ("спб", "Санкт-Петербург"),
        ("гомеля", "Гомель"),
        ("варшаву", "Варшава"),
        ("могилёва", "Могилёв"),
        ("могилева", "Могилёв"),
    ],
)
def test_canonical_city(raw, expected):
    assert canonical_city(raw) == expected


def test_canonical_city_unknown():
    assert canonical_city("Казань") is None
    assert canonical_city(None) is None


def test_canonical_body_type():
    assert canonical_body_type("рефрижератор") == "реф"
    assert canonical_body_type("tent") == "тент"
    assert canonical_body_type("еврофура") == "тент"
    assert canonical_body_type("изотермический") == "изотерм"


def test_canonical_payment():
    assert canonical_payment("безналичный") == "noncash"
    assert canonical_payment("cash") == "cash"
    assert canonical_payment("наличные") == "cash"


def test_detect_body_type_slang():
    assert detect_body_type("Еврофура из Бреста в Варшаву") == "тент"
    assert detect_body_type("Нужна фура 15 тонн") == "тент"
    assert detect_body_type("тентовка на 5 тонн") == "тент"
    assert detect_body_type("рефрижератор 10 т") == "реф"
    assert detect_body_type("изотермический фургон") == "изотерм"
    assert detect_body_type("бортовая машина") == "борт"
    assert detect_body_type("просто какой-то груз") is None
    assert detect_body_type(None) is None


def test_normalize_request_end_to_end():
    raw = {
        "origin": "минска",
        "destination": "москву",
        "body_type": "рефрижератор",
        "payment": "безнал",
        "load_type": "догруз",
        "weight_t": 10,
    }
    out = normalize_request(raw)
    assert out["origin"] == "Минск"
    assert out["destination"] == "Москва"
    assert out["body_type"] == "реф"
    assert out["payment"] == "noncash"
    assert out["load_type"] == "partial"
    assert out["weight_t"] == 10
