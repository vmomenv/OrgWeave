"""Shared pytest configuration.

Integration tests require real infrastructure:
    sg docker -c "make infra"   # or docker compose up -d ...
    make migrate
    ORGWEAVE_INTEGRATION=1 pytest -m integration
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _integration_gate() -> None:
    """Fail loudly when integration tests are requested without infrastructure."""
    if os.environ.get("ORGWEAVE_INTEGRATION") == "1":
        return
    return


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("ORGWEAVE_INTEGRATION") == "1":
        return
    skip = pytest.mark.skip(reason="set ORGWEAVE_INTEGRATION=1 and start docker compose")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
