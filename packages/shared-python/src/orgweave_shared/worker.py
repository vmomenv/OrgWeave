"""Worker heartbeat and shutdown primitives shared by every OrgWeave worker."""

from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import socket
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis

from orgweave_shared.logging import get_logger

logger = get_logger(__name__)

_WORKER_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
HEARTBEAT_KEY_PREFIX = "orgweave:worker"


def heartbeat_key(worker_name: str) -> str:
    """Return the deterministic Redis key for a worker's heartbeat."""
    if not _WORKER_NAME_RE.fullmatch(worker_name):
        raise ValueError(
            f"invalid worker name {worker_name!r}; use lowercase letters, digits and hyphens"
        )
    return f"{HEARTBEAT_KEY_PREFIX}:{worker_name}:heartbeat"


def build_heartbeat(
    worker_name: str,
    status: str,
    started_at: datetime,
    *,
    now: datetime | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Build the heartbeat hash written to Redis.

    Timestamps are UTC ISO-8601 so the watchdog and humans read the same value.
    """
    current = now or datetime.now(UTC)
    if started_at.tzinfo is None:
        raise ValueError("started_at must be timezone-aware")
    payload: dict[str, str] = {
        "worker": worker_name,
        "status": status,
        "started_at": started_at.astimezone(UTC).isoformat(),
        "updated_at": current.astimezone(UTC).isoformat(),
        "pid": str(os.getpid()),
        "hostname": socket.gethostname(),
    }
    if metadata:
        payload["metadata"] = json.dumps(dict(metadata), ensure_ascii=False, default=str)
    return payload


async def write_heartbeat(
    redis: Redis,
    worker_name: str,
    started_at: datetime,
    *,
    status: str = "running",
    metadata: Mapping[str, Any] | None = None,
    ttl_seconds: int = 60,
) -> dict[str, str]:
    """Write a heartbeat hash with a TTL.

    The TTL is the crash detector: a worker that dies stops refreshing its key,
    and the watchdog sees the key disappear or go stale.
    """
    key = heartbeat_key(worker_name)
    payload = build_heartbeat(worker_name, status, started_at, metadata=metadata)
    await redis.hset(key, mapping=payload)
    await redis.expire(key, ttl_seconds)
    return payload


async def heartbeat_loop(
    redis: Redis,
    worker_name: str,
    started_at: datetime,
    *,
    interval_seconds: float,
    stop_event: asyncio.Event,
    metadata: Mapping[str, Any] | None = None,
    ttl_seconds: int = 60,
) -> None:
    """Refresh the heartbeat until ``stop_event`` is set.

    Redis failures are logged and retried on the next interval; a transient
    outage must not kill a worker that is otherwise healthy.
    """
    while not stop_event.is_set():
        try:
            await write_heartbeat(
                redis,
                worker_name,
                started_at,
                metadata=metadata,
                ttl_seconds=ttl_seconds,
            )
        except Exception:
            logger.exception("heartbeat write failed", extra={"worker": worker_name})
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            continue


def install_signal_handlers(stop_event: asyncio.Event) -> None:
    """Request graceful shutdown on SIGINT/SIGTERM."""
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:  # pragma: no cover - Windows fallback
            signal.signal(sig, lambda *_: stop_event.set())
