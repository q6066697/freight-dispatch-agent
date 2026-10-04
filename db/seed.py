"""Build and populate data/freight.db with SYNTHETIC freight data.

Deterministic: a fixed RNG seed means the same database every run, so tests and
eval are reproducible. Run with:  python -m db.seed
"""

from __future__ import annotations

import os
import random
import sqlite3
from pathlib import Path

from app.config import get_settings

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

BODY_TYPES = ["тент", "реф", "изотерм", "борт"]

# Baseline tariff per body type (RUB/km) before per-carrier variation.
BASE_RATE = {"тент": 55.0, "реф": 78.0, "изотерм": 66.0, "борт": 50.0}

CITIES = [
    "Минск", "Брест", "Гомель", "Витебск", "Могилёв", "Гродно",
    "Москва", "Санкт-Петербург", "Смоленск", "Брянск", "Калининград",
    "Вильнюс", "Каунас", "Варшава", "Гданьск", "Лодзь",
]

# (origin, destination, distance_km) — inserted in BOTH directions.
ROUTE_PAIRS = [
    ("Минск", "Москва", 718),
    ("Минск", "Санкт-Петербург", 835),
    ("Минск", "Смоленск", 340),
    ("Минск", "Брест", 346),
    ("Минск", "Гомель", 302),
    ("Минск", "Витебск", 280),
    ("Минск", "Могилёв", 200),
    ("Минск", "Гродно", 280),
    ("Минск", "Вильнюс", 185),
    ("Минск", "Каунас", 290),
    ("Минск", "Варшава", 550),
    ("Минск", "Калининград", 600),
    ("Минск", "Брянск", 480),
    ("Москва", "Санкт-Петербург", 710),
    ("Москва", "Смоленск", 400),
    ("Москва", "Брянск", 380),
    ("Брест", "Варшава", 210),
    ("Брест", "Москва", 1060),
    ("Гомель", "Москва", 690),
    ("Вильнюс", "Каунас", 100),
    ("Варшава", "Гданьск", 340),
    ("Варшава", "Лодзь", 135),
]

CARRIER_NAMES = [
    ("ТОО «БелТрансЛогистик»", "Минск"),
    ("ИП Ковалёв А.С.", "Минск"),
    ("ООО «Запад-Карго»", "Брест"),
    ("ТранзитАвто", "Гомель"),
    ("ИП Савицкий В.П.", "Витебск"),
    ("ООО «Евродоставка»", "Москва"),
    ("АвтоПуть", "Смоленск"),
    ("ИП Мороз Д.И.", "Гродно"),
    ("ООО «СеверТранс»", "Санкт-Петербург"),
    ("Балтик Лайн", "Калининград"),
    ("ИП Петров С.Н.", "Брянск"),
    ("ООО «Виа-Карго»", "Вильнюс"),
    ("ПольшаТранс", "Варшава"),
    ("ИП Романюк К.А.", "Могилёв"),
    ("ООО «ГрузСервис»", "Минск"),
]


def _rng() -> random.Random:
    return random.Random(20260101)  # fixed seed → reproducible DB


def _db_path() -> Path:
    path = Path(get_settings().freight_db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def build(db_path: Path | None = None) -> Path:
    path = db_path or _db_path()
    if path.exists():
        path.unlink()

    rng = _rng()
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

        # --- carriers ---
        carriers: list[tuple] = []
        for i, (name, city) in enumerate(CARRIER_NAMES, start=1):
            rating = round(rng.uniform(3.6, 5.0), 1)
            payment = rng.choice(["cash", "noncash", "both", "both"])
            vat = 1 if payment in ("noncash", "both") and rng.random() < 0.7 else 0
            phone = f"+375{rng.randint(25, 44)}{rng.randint(1000000, 9999999)}"
            carriers.append((i, name, city, phone, rating, payment, vat))
        conn.executemany(
            "INSERT INTO carriers (id,name,home_city,phone,rating,payment_terms,vat) "
            "VALUES (?,?,?,?,?,?,?)",
            carriers,
        )

        # --- routes (both directions) ---
        route_rows: list[tuple] = []
        rid = 1
        for origin, dest, dist in ROUTE_PAIRS:
            route_rows.append((rid, origin, dest, dist))
            rid += 1
            route_rows.append((rid, dest, origin, dist))
            rid += 1
        conn.executemany(
            "INSERT INTO routes (id,origin,destination,distance_km) VALUES (?,?,?,?)",
            route_rows,
        )

        # --- trucks (~40) ---
        trucks: list[tuple] = []
        plate_letters = "АВЕКМНОРСТУХ"
        for tid in range(1, 41):
            carrier_id = rng.randint(1, len(CARRIER_NAMES))
            body = rng.choices(BODY_TYPES, weights=[5, 2, 2, 2])[0]
            if body in ("тент", "реф"):
                capacity = rng.choice([3.0, 5.0, 10.0, 20.0, 20.0, 20.0])
            else:
                capacity = rng.choice([1.5, 3.0, 5.0, 10.0, 15.0, 20.0])
            # Volume roughly tracks capacity; euro-tent full truck ~ 86-92 m3.
            vol_map = {20.0: 86.0, 15.0: 60.0, 10.0: 45.0, 5.0: 28.0, 3.0: 18.0, 1.5: 10.0}
            volume = vol_map[capacity] + rng.choice([-4, -2, 0, 2, 6])
            city = rng.choice(CITIES)
            status = "free" if rng.random() < 0.75 else "busy"
            plate = (
                f"{rng.choice(plate_letters)}{rng.randint(100, 999)}"
                f"{rng.choice(plate_letters)}{rng.choice(plate_letters)}"
            )
            trucks.append((tid, carrier_id, plate, body, capacity, round(volume, 1), city, status))
        conn.executemany(
            "INSERT INTO trucks (id,carrier_id,plate,body_type,capacity_t,volume_m3,"
            "current_city,status) VALUES (?,?,?,?,?,?,?,?)",
            trucks,
        )

        # --- rates (one per carrier per body type they actually own) ---
        owned: dict[tuple[int, str], bool] = {}
        for (_tid, carrier_id, _p, body, *_rest) in trucks:
            owned[(carrier_id, body)] = True
        rate_rows: list[tuple] = []
        rate_id = 1
        for (carrier_id, body) in sorted(owned):
            variation = rng.uniform(0.88, 1.18)
            rate = round(BASE_RATE[body] * variation, 1)
            min_price = round(rng.choice([12000, 15000, 18000]) * variation, -2)
            rate_rows.append((rate_id, carrier_id, body, rate, min_price, "RUB"))
            rate_id += 1
        conn.executemany(
            "INSERT INTO rates (id,carrier_id,body_type,rate_per_km,min_price,currency) "
            "VALUES (?,?,?,?,?,?)",
            rate_rows,
        )

        conn.commit()
    finally:
        conn.close()
    return path


def summarize(path: Path) -> str:
    conn = sqlite3.connect(path)
    try:
        c = conn.cursor()
        counts = {
            t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("carriers", "trucks", "routes", "rates")
        }
    finally:
        conn.close()
    return ", ".join(f"{k}={v}" for k, v in counts.items())


if __name__ == "__main__":
    out = build()
    print(f"Built {out.resolve()} ({os.path.getsize(out)} bytes)")
    print("Rows:", summarize(out))
