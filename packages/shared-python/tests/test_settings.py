from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from orgweave_shared.settings import OrgWeaveSettings


def test_settings_have_working_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "DATABASE_URL",
        "REDIS_URL",
        "HEALTH_CHECK_TIMEOUT_SECONDS",
        "CORS_ORIGINS",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = OrgWeaveSettings(_env_file=None)

    assert settings.api_port == 8000
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.health_check_timeout_seconds == 3.0


def test_settings_read_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_PORT", "9100")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000, https://app.example.com")
    monkeypatch.setenv("HEALTH_CHECK_TIMEOUT_SECONDS", "1.5")

    settings = OrgWeaveSettings(_env_file=None)

    assert settings.api_port == 9100
    assert settings.cors_origin_list == [
        "http://localhost:3000",
        "https://app.example.com",
    ]
    assert settings.health_check_timeout_seconds == 1.5


def test_database_scheme_is_enforced() -> None:
    with pytest.raises(ValidationError, match="postgresql\\+asyncpg"):
        OrgWeaveSettings(_env_file=None, database_url="sqlite:///local.db")


def test_redis_scheme_is_enforced() -> None:
    with pytest.raises(ValidationError, match="redis://"):
        OrgWeaveSettings(_env_file=None, redis_url="http://localhost:6379")


def test_heartbeat_timeout_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        OrgWeaveSettings(_env_file=None, health_check_timeout_seconds=0)


def test_worker_metadata_is_json_encoded() -> None:
    from orgweave_shared.worker import build_heartbeat

    started = datetime(2026, 11, 17, 9, 0, tzinfo=UTC)
    payload = build_heartbeat(
        "agent-worker",
        "running",
        started,
        now=datetime(2026, 11, 17, 9, 0, 10, tzinfo=UTC),
        metadata={"queue": "orgweave:agent:jobs", "concurrency": 2},
    )

    assert payload["worker"] == "agent-worker"
    assert payload["status"] == "running"
    assert payload["updated_at"] == "2026-11-17T09:00:10+00:00"
    assert json.loads(payload["metadata"]) == {
        "queue": "orgweave:agent:jobs",
        "concurrency": 2,
    }
    assert payload["pid"].isdigit()


def test_heartbeat_key_rejects_unsafe_names() -> None:
    from orgweave_shared.worker import heartbeat_key

    assert heartbeat_key("agent-worker") == "orgweave:worker:agent-worker:heartbeat"
    with pytest.raises(ValueError):
        heartbeat_key("../escape")
