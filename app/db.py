"""Database access helpers.

The SQL agent must only ever touch the DB through `readonly_connection()`, which
opens SQLite in read-only URI mode. Even a query that somehow slipped past the SQL
guard cannot write or run DDL on this connection.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import get_settings

# Tables the SQL agent is allowed to read. Kept here so the guard and the rest of
# the app agree on one source of truth.
ALLOWED_TABLES = frozenset({"carriers", "trucks", "routes", "rates"})


def db_path() -> Path:
    return Path(get_settings().freight_db_path)


def readonly_connection() -> sqlite3.Connection:
    """Open the freight DB read-only. Raises if the file is missing."""
    path = db_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Database not found at {path}. Build it first: python -m db.seed"
        )
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn
