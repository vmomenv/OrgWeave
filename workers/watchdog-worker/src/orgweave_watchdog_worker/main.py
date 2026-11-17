"""Watchdog Worker entrypoint."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime

from orgweave_shared import (
    OrgWeaveSettings,
    configure_logging,
    create_redis,
    heartbeat_loop,
    install_signal_handlers,
    write_heartbeat,
)
from redis.exceptions import RedisError

from orgweave_watchdog_worker.detector import emit_alerts, scan_heartbeats

logger = logging.getLogger("orgweave.watchdog_worker")
DEFAULT_WORKER_NAME = "watchdog-worker"


async def scan_forever(
    settings: OrgWeaveSettings,
    *,
    stop_event: asyncio.Event,
) -> None:
    redis = create_redis(settings)
    try:
        while not stop_event.is_set():
            try:
                alerts = await scan_heartbeats(
                    redis,
                    now=datetime.now(UTC),
                    stale_after_seconds=settings.watchdog_stale_after_seconds,
                )
                if alerts:
                    await emit_alerts(redis, alerts)
                else:
                    logger.debug("watchdog scan clean")
            except RedisError:
                logger.exception("watchdog scan failed")
            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=settings.watchdog_scan_interval_seconds
                )
            except TimeoutError:
                continue
    finally:
        await redis.aclose()


async def run() -> None:
    settings = OrgWeaveSettings()
    configure_logging(settings.log_level)
    worker_name = os.environ.get("WORKER_NAME") or DEFAULT_WORKER_NAME
    started_at = datetime.now(UTC)
    stop_event = asyncio.Event()
    install_signal_handlers(stop_event)

    redis = create_redis(settings)
    heartbeat_task = asyncio.create_task(
        heartbeat_loop(
            redis,
            worker_name,
            started_at,
            interval_seconds=settings.worker_heartbeat_interval_seconds,
            stop_event=stop_event,
            metadata={
                "scan_interval": settings.watchdog_scan_interval_seconds,
                "stale_after": settings.watchdog_stale_after_seconds,
            },
            ttl_seconds=max(int(settings.worker_heartbeat_interval_seconds * 6), 30),
        )
    )
    logger.info("watchdog scanning", extra={"worker": worker_name})
    try:
        await scan_forever(settings, stop_event=stop_event)
    finally:
        stop_event.set()
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        await write_heartbeat(redis, worker_name, started_at, status="stopped", ttl_seconds=10)
        await redis.aclose()
        logger.info("watchdog stopped", extra={"worker": worker_name})


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
