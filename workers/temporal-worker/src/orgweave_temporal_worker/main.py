"""Temporal Worker entrypoint."""

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
from temporalio.client import Client
from temporalio.worker import Worker

from orgweave_temporal_worker.activities import ping_activity
from orgweave_temporal_worker.workflows import PingWorkflow

logger = logging.getLogger("orgweave.temporal_worker")
DEFAULT_WORKER_NAME = "temporal-worker"


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
                "task_queue": settings.temporal_task_queue,
                "temporal": settings.temporal_host,
            },
            ttl_seconds=max(int(settings.worker_heartbeat_interval_seconds * 6), 30),
        )
    )

    client = await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)
    logger.info(
        "temporal worker connected",
        extra={"worker": worker_name, "queue": settings.temporal_task_queue},
    )

    try:
        async with Worker(
            client,
            task_queue=settings.temporal_task_queue,
            workflows=[PingWorkflow],
            activities=[ping_activity],
        ):
            await stop_event.wait()
    finally:
        stop_event.set()
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        await write_heartbeat(redis, worker_name, started_at, status="stopped", ttl_seconds=10)
        await redis.aclose()
        logger.info("temporal worker stopped", extra={"worker": worker_name})


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
