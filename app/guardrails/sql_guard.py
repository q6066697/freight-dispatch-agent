"""SQL guardrail for the text-to-SQL agent.

Philosophy: never trust a generated query. We parse it into an AST with `sqlglot`
and accept it only if it is a single read-only SELECT over whitelisted tables, with
no comment tricks, no stacked statements, no PRAGMA/ATTACH/DDL/DML, and no dangerous
functions. A LIMIT is injected/clamped so a query can never scan unbounded rows.

The sanitized SQL returned by `validate_sql` is what the agent executes — and it is
executed on a read-only connection (`app/db.py`), so this guard is one of two layers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from app.db import ALLOWED_TABLES

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

# Fast pre-filter: a pure SELECT never legitimately contains these.
_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(PRAGMA|ATTACH|DETACH|VACUUM|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|"
    r"REPLACE|TRUNCATE|GRANT|REVOKE|BEGIN|COMMIT|ROLLBACK|REINDEX|ANALYZE|"
    r"SAVEPOINT|RELEASE)\b",
    re.IGNORECASE,
)

# Dangerous SQLite functions that could touch the filesystem / load code.
_FORBIDDEN_FUNCS = {
    "load_extension",
    "readfile",
    "writefile",
    "edit",
    "fts3_tokenizer",
    "zipfile",
}

# AST node types that must never appear anywhere in an accepted query.
_FORBIDDEN_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.Command,     # PRAGMA / VACUUM / ATTACH etc. parse to Command in sqlite
    exp.Set,
    exp.Transaction,
)


@dataclass
class GuardResult:
    ok: bool
    sql: str | None = None            # sanitized SQL to execute (when ok)
    reason: str | None = None         # human-readable rejection reason
    tables: set[str] = field(default_factory=set)


class SQLGuardError(Exception):
    """Raised by `guard_sql` when a query is rejected."""


def _limit_value(select: exp.Expression) -> int | None:
    node = select.args.get("limit")
    if node is None:
        return None
    try:
        return int(node.expression.name)
    except (AttributeError, ValueError, TypeError):
        return None


def validate_sql(
    sql: str,
    *,
    allowed_tables: frozenset[str] | set[str] = ALLOWED_TABLES,
    default_limit: int = DEFAULT_LIMIT,
    max_limit: int = MAX_LIMIT,
) -> GuardResult:
    """Validate and sanitize a candidate SQL string. Never executes anything."""
    if sql is None or not sql.strip():
        return GuardResult(ok=False, reason="empty query")

    raw = sql.strip()

    # 1) Comment tricks (-- , /* */) — reject outright; a legit SELECT needs none.
    if "--" in raw or "/*" in raw or "*/" in raw:
        return GuardResult(ok=False, reason="SQL comments are not allowed")

    # 2) Stacked statements via semicolons (allow a single trailing one).
    body = raw[:-1].rstrip() if raw.endswith(";") else raw
    if ";" in body:
        return GuardResult(ok=False, reason="multiple statements are not allowed")

    # 3) Keyword pre-filter (cheap, before parsing).
    if _FORBIDDEN_KEYWORDS.search(body):
        return GuardResult(ok=False, reason="forbidden keyword (non-SELECT operation)")

    # 4) Parse to AST.
    try:
        statements = sqlglot.parse(body, dialect="sqlite")
    except Exception as e:  # noqa: BLE001 - sqlglot raises various parse errors
        return GuardResult(ok=False, reason=f"SQL parse error: {e}")

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        return GuardResult(ok=False, reason="exactly one statement is required")

    root = statements[0]

    # 5) Root must be a SELECT (or a UNION/INTERSECT/EXCEPT of selects).
    if not isinstance(root, (exp.Select, exp.Union)):
        return GuardResult(ok=False, reason="only SELECT queries are allowed")

    # 6) No forbidden node types anywhere in the tree.
    for node_type in _FORBIDDEN_NODES:
        if root.find(node_type) is not None:
            return GuardResult(ok=False, reason="query contains a non-SELECT operation")

    # 7) No dangerous functions.
    for func in root.find_all(exp.Anonymous):
        name = (func.name or "").lower()
        if name in _FORBIDDEN_FUNCS:
            return GuardResult(ok=False, reason=f"function '{name}' is not allowed")
    for func in root.find_all(exp.Func):
        name = (func.sql_name() or "").lower() if hasattr(func, "sql_name") else ""
        if name in _FORBIDDEN_FUNCS:
            return GuardResult(ok=False, reason=f"function '{name}' is not allowed")

    # 8) Every referenced table must be whitelisted.
    allowed_lower = {t.lower() for t in allowed_tables}
    tables: set[str] = set()
    for tbl in root.find_all(exp.Table):
        tname = tbl.name.lower()
        tables.add(tbl.name)
        if tname not in allowed_lower:
            return GuardResult(
                ok=False,
                reason=f"table '{tbl.name}' is not in the allowed list",
                tables=tables,
            )
    if not tables:
        return GuardResult(ok=False, reason="query references no tables")

    # 9) Enforce / clamp LIMIT on the outermost query.
    existing = _limit_value(root)
    effective = default_limit if existing is None else min(existing, max_limit)
    root = root.limit(effective)

    sanitized = root.sql(dialect="sqlite")
    return GuardResult(ok=True, sql=sanitized, tables=tables)


def guard_sql(sql: str, **kwargs) -> str:
    """Convenience wrapper: return sanitized SQL or raise SQLGuardError."""
    result = validate_sql(sql, **kwargs)
    if not result.ok:
        raise SQLGuardError(result.reason)
    assert result.sql is not None
    return result.sql
