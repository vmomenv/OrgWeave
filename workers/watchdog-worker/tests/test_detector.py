from __future__ import annotations

from datetime import UTC, datetime, timedelta

from orgweave_watchdog_worker.detector import inspect_heartbeat

NOW = datetime(2026, 11, 17, 10, 0, tzinfo=UTC)


def test_fresh_heartbeat_has_no_alert() -> None:
    key = "orgweave:worker:agent-worker:heartbeat"
    data = {"status": "running", "updated_at": (NOW - timedelta(seconds=10)).isoformat()}

    assert inspect_heartbeat(key, data, now=NOW, stale_after_seconds=45) is None


def test_stale_heartbeat_is_detected() -> None:
    key = "orgweave:worker:agent-worker:heartbeat"
    data = {"status": "running", "updated_at": (NOW - timedelta(seconds=90)).isoformat()}

    alert = inspect_heartbeat(key, data, now=NOW, stale_after_seconds=45)

    assert alert is not None
    assert alert.worker == "agent-worker"
    assert alert.reason == "stale_heartbeat"
    assert alert.age_seconds == 90


def test_invalid_timestamp_is_detected() -> None:
    alert = inspect_heartbeat(
        "orgweave:worker:skill-runner:heartbeat",
        {"status": "running", "updated_at": "yesterday"},
        now=NOW,
        stale_after_seconds=45,
    )

    assert alert is not None
    assert alert.reason == "invalid_timestamp"


def test_missing_timestamp_is_detected() -> None:
    alert = inspect_heartbeat(
        "orgweave:worker:temporal-worker:heartbeat",
        {"status": "running"},
        now=NOW,
        stale_after_seconds=45,
    )

    assert alert is not None
    assert alert.reason == "missing_timestamp"
