"""Shared fixtures.

Force mock mode and ensure the synthetic DB exists, so the suite is fully offline
and deterministic even if the developer's local .env sets a real provider (e.g.
LLM_PROVIDER=ollama for manual CPU runs).
"""

import os

import pytest

from app.config import get_settings
from app.db import db_path
from db.seed import build


@pytest.fixture(scope="session", autouse=True)
def _offline_mock_env():
    os.environ["LLM_PROVIDER"] = "mock"  # env var overrides any .env value
    get_settings.cache_clear()

    import app.graph as graph_module
    graph_module._GRAPH_CACHE.clear()

    if not db_path().exists():
        build()
    yield
