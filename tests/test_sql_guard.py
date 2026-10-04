"""SQL guard tests — heavy on attack vectors."""

import pytest

from app.guardrails.sql_guard import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    SQLGuardError,
    guard_sql,
    validate_sql,
)

VALID_QUERIES = [
    "SELECT * FROM trucks WHERE body_type='тент'",
    "SELECT id, name FROM carriers WHERE rating > 4.0",
    "SELECT t.plate, c.name FROM trucks t JOIN carriers c ON c.id=t.carrier_id",
    "SELECT distance_km FROM routes WHERE origin='Минск' AND destination='Москва'",
    "SELECT body_type, COUNT(*) FROM trucks GROUP BY body_type HAVING COUNT(*) > 1",
    "SELECT * FROM trucks WHERE status='free' ORDER BY capacity_t DESC LIMIT 10",
    "SELECT carrier_id, rate_per_km FROM rates WHERE body_type='реф' "
    "UNION SELECT carrier_id, rate_per_km FROM rates WHERE body_type='тент'",
]

ATTACKS = [
    # stacked statement / data mutation
    "SELECT * FROM trucks; DROP TABLE trucks",
    "SELECT * FROM carriers; DELETE FROM carriers",
    "DROP TABLE carriers",
    "DELETE FROM trucks WHERE 1=1",
    "UPDATE rates SET rate_per_km=0",
    "INSERT INTO carriers (name) VALUES ('x')",
    # comment tricks
    "SELECT * FROM trucks -- ignore the limit",
    "SELECT * FROM trucks /* sneaky */ WHERE 1=1",
    "SELECT * FROM carriers;--",
    # pragma / attach / filesystem
    "PRAGMA table_info(carriers)",
    "ATTACH DATABASE 'evil.db' AS evil",
    "SELECT load_extension('evil.so')",
    "SELECT readfile('/etc/passwd')",
    # unknown / system tables
    "SELECT * FROM sqlite_master",
    "SELECT sql FROM sqlite_master WHERE type='table'",
    "SELECT * FROM users",
    "SELECT * FROM secret_keys",
    # non-select root
    "VACUUM",
    "WITH x AS (SELECT 1) DELETE FROM trucks",
    # garbage / empty
    "",
    "not sql at all ;;;",
]


@pytest.mark.parametrize("sql", VALID_QUERIES)
def test_valid_queries_pass(sql):
    res = validate_sql(sql)
    assert res.ok, f"should pass: {sql} -> {res.reason}"
    assert res.sql is not None
    assert "limit" in res.sql.lower()


@pytest.mark.parametrize("sql", ATTACKS)
def test_attacks_blocked(sql):
    res = validate_sql(sql)
    assert not res.ok, f"should be blocked: {sql!r}"
    assert res.reason


def test_limit_injected_when_absent():
    res = validate_sql("SELECT * FROM trucks")
    assert res.ok
    assert f"LIMIT {DEFAULT_LIMIT}".lower() in res.sql.lower()


def test_limit_clamped_when_too_large():
    res = validate_sql("SELECT * FROM trucks LIMIT 100000")
    assert res.ok
    assert str(MAX_LIMIT) in res.sql
    assert "100000" not in res.sql


def test_small_limit_preserved():
    res = validate_sql("SELECT * FROM trucks LIMIT 5")
    assert res.ok
    assert "5" in res.sql


def test_table_whitelist_enforced():
    res = validate_sql("SELECT * FROM carriers", allowed_tables={"trucks"})
    assert not res.ok
    assert "allowed" in res.reason


def test_guard_sql_raises_on_attack():
    with pytest.raises(SQLGuardError):
        guard_sql("DROP TABLE carriers")


def test_guard_sql_returns_sanitized():
    out = guard_sql("SELECT id FROM carriers")
    assert out.lower().startswith("select")
    assert "limit" in out.lower()


def test_tables_reported():
    res = validate_sql("SELECT * FROM trucks t JOIN carriers c ON c.id=t.carrier_id")
    assert res.ok
    assert res.tables == {"trucks", "carriers"}
