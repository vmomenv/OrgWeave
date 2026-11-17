"""Repository-wide pytest behavior.

Integration tests require real infrastructure:
    make infra        # PostgreSQL, Redis, Temporal, LiteLLM, MinIO
    make migrate
    ORGWEAVE_INTEGRATION=1 make test
"""

from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("ORGWEAVE_INTEGRATION") == "1":
        return
    skip = pytest.mark.skip(reason="set ORGWEAVE_INTEGRATION=1 and start docker compose")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
