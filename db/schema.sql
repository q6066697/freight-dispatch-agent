-- freight-dispatch-agent database schema (SQLite).
-- All data is SYNTHETIC. Prices/distances are plausible but invented.

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS rates;
DROP TABLE IF EXISTS trucks;
DROP TABLE IF EXISTS routes;
DROP TABLE IF EXISTS carriers;

-- Freight carriers (companies / sole proprietors).
CREATE TABLE carriers (
    id            INTEGER PRIMARY KEY,
    name          TEXT    NOT NULL,
    home_city     TEXT    NOT NULL,
    phone         TEXT    NOT NULL,
    rating        REAL    NOT NULL,              -- 1.0 .. 5.0
    payment_terms TEXT    NOT NULL,              -- 'cash' | 'noncash' | 'both'
    vat           INTEGER NOT NULL DEFAULT 0     -- 0/1: works with VAT (НДС)
);

-- Trucks belonging to carriers.
CREATE TABLE trucks (
    id           INTEGER PRIMARY KEY,
    carrier_id   INTEGER NOT NULL REFERENCES carriers(id),
    plate        TEXT    NOT NULL,
    body_type    TEXT    NOT NULL,               -- 'тент' | 'реф' | 'изотерм' | 'борт'
    capacity_t   REAL    NOT NULL,               -- payload capacity, tonnes
    volume_m3    REAL    NOT NULL,               -- cargo volume, cubic metres
    current_city TEXT    NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'free' -- 'free' | 'busy'
);

-- Known city pairs with road distances (directional rows inserted both ways).
CREATE TABLE routes (
    id           INTEGER PRIMARY KEY,
    origin       TEXT    NOT NULL,
    destination  TEXT    NOT NULL,
    distance_km  INTEGER NOT NULL,
    UNIQUE (origin, destination)
);

-- Per-carrier, per-body-type tariff sheet.
CREATE TABLE rates (
    id          INTEGER PRIMARY KEY,
    carrier_id  INTEGER NOT NULL REFERENCES carriers(id),
    body_type   TEXT    NOT NULL,
    rate_per_km REAL    NOT NULL,                -- currency units per km
    min_price   REAL    NOT NULL,               -- minimum charge for a trip
    currency    TEXT    NOT NULL DEFAULT 'RUB',
    UNIQUE (carrier_id, body_type)
);

CREATE INDEX idx_trucks_body   ON trucks(body_type);
CREATE INDEX idx_trucks_city   ON trucks(current_city);
CREATE INDEX idx_trucks_status ON trucks(status);
CREATE INDEX idx_routes_od     ON routes(origin, destination);
CREATE INDEX idx_rates_carrier ON rates(carrier_id, body_type);
