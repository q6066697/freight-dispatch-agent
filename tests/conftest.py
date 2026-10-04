"""Shared fixtures: make sure the synthetic DB exists before DB-backed tests."""

import pytest

from app.db import db_path
from db.seed import build


@pytest.fixture(scope="session", autouse=True)
def ensure_db():
    if not db_path().exists():
        build()
    yield
