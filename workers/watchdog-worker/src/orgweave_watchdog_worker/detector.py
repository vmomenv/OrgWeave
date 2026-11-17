"""Deterministic heartbeat staleness detection."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

ALERT_CHANNEL = "orgweave:watchdog:alerts"
HEARTBEAT_PATTERN = "orgweave:worker:*:heartbeat"


@dataclass(frozen=True)
class StaleHeartbeat:
    worker: str
    key: str
    status: str
    updated_at: str | None
    age_seconds: float | None
    reason: str


def inspect_heartbeat(
    key: str,
    data: dict[str, str],
    *,
    now: datetime,
    stale_after_seconds: float,
) -> StaleHeartbeat | None:
    """Return an alert when a heartbeat is stale or malformed."""
    worker = key.split(":")[2] if len(key.split(":")) >= 4 else key
    status = data.get("status", "unknown")
    updated_at = data.get("updated_at")

    if not data:
        return StaleHeartbeat(
            worker=worker,
            key=key,
            status=status,
            updated_at=None,
            age_seconds=None,
            reason="expired_heartbeat",
        )
    if not updated_at:
        return StaleHeartbeat(
            worker=worker,
            key=key,
            status=status,
            updated_at=None,
            age_seconds=None,
            reason="missing_timestamp",
        )
    try:
        updated = datetime.fromisoformat(updated_at)
    except ValueError:
        return StaleHeartbeat(
            worker=worker,
            key=key,
            status=status,
            updated_at=updated_at,
            age_seconds=None,
            reason="invalid_timestamp",
        )
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    age = (now.astimezone(UTC) - updated.astimezone(UTC)).total_seconds()
    if age > stale_after_seconds:
        return StaleHeartbeat(
            worker=worker,
            key=key,
            status=status,
            updated_at=updated_at,
            age_seconds=age,
            reason="stale_heartbeat",
        )
    return None


async def scan_heartbeats(
    redis: Redis,
    *,
    now: datetime,
    stale_after_seconds: float,
) -> list[StaleHeartbeat]:
    alerts: list[StaleHeartbeat] = []
    async for key in redis.scan_iter(match=HEARTBEAT_PATTERN, count=100):
        data = await redis.hgetall(key)
        alert = inspect_heartbeat(key, data, now=now, stale_after_seconds=stale_after_seconds)
        if alert is not None:
            alerts.append(alert)
    return alerts


async def emit_alerts(
    redis: Redis,
    alerts: list[StaleHeartbeat],
    *,
    channel: str = ALERT_CHANNEL,
) -> None:
    for alert in alerts:
        payload = json.dumps(
            {"type": "worker_heartbeat_alert", **asdict(alert)}, ensure_ascii=False
        )
        await redis.publish(channel, payload)
        logger.warning(
            "worker heartbeat alert: %s (%s)",
            alert.worker,
            alert.reason,
            extra={"worker": alert.worker},
        )
