from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from orgweave_skill_runner.main import app


def test_liveness_returns_service_identity() -> None:
    with TestClient(app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "orgweave-skill-runner"


@pytest.mark.integration
def test_readiness_checks_real_redis() -> None:
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["detail"] == "ping=ok"
