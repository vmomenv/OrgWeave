from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from app.api.deps import get_health_probes
from app.infrastructure.health.probes import Probe
from app.main import app
from app.schemas.health import DependencyCheck
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> AsyncIterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _ok_probe(name: str) -> Probe:
    async def check() -> DependencyCheck:
        return DependencyCheck(name=name, status="ok", latency_ms=1.0, detail="stub-ok")

    return Probe(name, check)


def _failing_probe(name: str) -> Probe:
    async def check() -> DependencyCheck:
        raise ConnectionError("connect postgresql://user:secret-password@db:5432/x failed")

    return Probe(name, check)


def test_liveness_is_process_only(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "orgweave-api"
    assert body["version"] == "0.1.0"
    assert "timestamp" in body


def test_readiness_is_ready_when_all_probes_pass(client: TestClient) -> None:
    app.dependency_overrides[get_health_probes] = lambda: [
        _ok_probe("postgres"),
        _ok_probe("redis"),
    ]

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert [check["name"] for check in body["checks"]] == ["postgres", "redis"]


def test_readiness_degrades_and_redacts_credentials(client: TestClient) -> None:
    app.dependency_overrides[get_health_probes] = lambda: [
        _ok_probe("postgres"),
        _failing_probe("redis"),
    ]

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    redis_check = next(check for check in body["checks"] if check["name"] == "redis")
    assert redis_check["status"] == "error"
    assert "ConnectionError" in redis_check["detail"]
    assert "secret-password" not in redis_check["detail"]
    assert "postgresql://***@db:5432/x" in redis_check["detail"]


def test_probe_timeout_is_reported(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from app.api.v1 import health as health_module

    async def slow() -> DependencyCheck:
        await asyncio.sleep(5)
        return DependencyCheck(name="slow", status="ok", latency_ms=1)

    app.dependency_overrides[get_health_probes] = lambda: [Probe("slow", slow)]
    monkeypatch.setattr(health_module, "get_settings", lambda: _SettingsWithTimeout(0.05))

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    check = response.json()["checks"][0]
    assert check["name"] == "slow"
    assert "timed out" in check["detail"]


class _SettingsWithTimeout:
    def __init__(self, timeout: float) -> None:
        self.health_check_timeout_seconds = timeout
        self.app_version = "0.1.0"


def test_meta_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/meta")

    assert response.status_code == 200
    body = response.json()
    assert body["phase"] == "0"
    assert body["api_prefix"] == "/api/v1"
    assert body["ws_prefix"] == "/ws/v1"


def test_openapi_is_served(client: TestClient) -> None:
    response = client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    schema: dict[str, Any] = response.json()
    assert "/api/v1/health/ready" in schema["paths"]
    assert "/api/v1/meta" in schema["paths"]


def test_request_id_header_is_echoed(client: TestClient) -> None:
    response = client.get("/api/v1/health/live", headers={"x-request-id": "abc123"})

    assert response.headers["x-request-id"] == "abc123"


def test_websocket_handshake_and_ping(client: TestClient) -> None:
    with client.websocket_connect("/ws/v1") as websocket:
        hello = websocket.receive_json()
        assert hello["type"] == "hello"
        assert hello["service"] == "orgweave-api"

        websocket.send_json({"type": "ping"})
        pong = websocket.receive_json()
        assert pong["type"] == "pong"

        websocket.send_text("not-json")
        error = websocket.receive_json()
        assert error["type"] == "error"
        assert error["reason"] == "invalid_json"
