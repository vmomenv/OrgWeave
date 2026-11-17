"""Shared pytest configuration for API tests."""

from __future__ import annotations

import os

# Keep test-enqueued jobs away from a running development Agent Worker.
os.environ.setdefault("AGENT_QUEUE", "orgweave:test:agent:jobs")

from collections.abc import Iterator

import pytest
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
