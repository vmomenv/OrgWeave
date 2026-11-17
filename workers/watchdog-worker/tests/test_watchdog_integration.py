"""Watchdog scan and alert delivery against real Redis."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from orgweave_shared import OrgWeaveSettings, create_redis
from orgweave_watchdog_worker.detector import emit_alerts, scan_heartbeats

pytestmark = pytest.mark.integration


@pytest.fixture
async def redis():
    client = create_redis(OrgWeaveSettings())
    yield client
    await client.aclose()


async def test_scan_finds_stale_heartbeat(redis) -> None:
    key = "orgweave:worker:test-stale-worker:heartbeat"
    now = datetime.now(UTC)
    await redis.hset(
        key,
        mapping={
            "worker": "test-stale-worker",
            "status": "running",
            "updated_at": (now - timedelta(minutes=5)).isoformat(),
        },
    )
    await redis.expire(key, 60)

    alerts = await scan_heartbeats(redis, now=now, stale_after_seconds=45)

    await redis.delete(key)
    matching = [alert for alert in alerts if alert.worker == "test-stale-worker"]
    assert len(matching) == 1
    assert matching[0].reason == "stale_heartbeat"


async def test_alerts_are_published_to_redis_channel(redis) -> None:
    from orgweave_watchdog_worker.detector import StaleHeartbeat

    channel = "orgweave:test:watchdog:alerts"
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    try:
        await pubsub.get_message(timeout=1)
        alert = StaleHeartbeat(
            worker="test-worker",
            key="orgweave:worker:test-worker:heartbeat",
            status="running",
            updated_at=datetime.now(UTC).isoformat(),
            age_seconds=120,
            reason="stale_heartbeat",
        )
        await emit_alerts(redis, [alert], channel=channel)
        message = None
        for _ in range(20):
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
            if message is not None:
                break
            await asyncio.sleep(0.05)
        assert message is not None
        payload = json.loads(message["data"])
        assert payload["worker"] == "test-worker"
        assert payload["reason"] == "stale_heartbeat"
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
