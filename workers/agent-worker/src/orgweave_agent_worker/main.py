"""Agent Worker entrypoint."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime

from app.core.db import create_engine, create_session_factory
from orgweave_shared import (
    OrgWeaveSettings,
    configure_logging,
    create_redis,
    heartbeat_loop,
    install_signal_handlers,
    write_heartbeat,
)
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import async_sessionmaker

from orgweave_agent_worker.jobs import DEAD_LETTER_QUEUE, RESULTS_QUEUE, dispatch
from orgweave_agent_worker.runner import handle_agent_run

logger = logging.getLogger("orgweave.agent_worker")
DEFAULT_WORKER_NAME = "agent-worker"


async def consume_forever(
    settings: OrgWeaveSettings,
    *,
    worker_name: str,
    stop_event: asyncio.Event,
    session_factory: async_sessionmaker | None = None,
) -> None:
    redis = create_redis(settings)
    logger.info(
        "agent worker consuming",
        extra={"worker": worker_name, "queue": settings.agent_queue},
    )
    try:
        while not stop_event.is_set():
            try:
                item = await redis.brpop([settings.agent_queue], timeout=2)
            except RedisError:
                logger.exception("queue read failed", extra={"worker": worker_name})
                await asyncio.sleep(1)
                continue
            if item is None:
                continue
            _, raw = item
            from orgweave_agent_sdk import AgentJob
            from pydantic import ValidationError

            try:
                job = AgentJob.model_validate_json(raw)
            except ValidationError:
                await dispatch(
                    redis,
                    raw,
                    worker_name=worker_name,
                    results_queue=RESULTS_QUEUE,
                    dead_letter_queue=settings.agent_dead_letter_queue or DEAD_LETTER_QUEUE,
                )
                continue

            if job.type == "agent.run" and session_factory is not None:
                try:
                    await handle_agent_run(redis, settings, session_factory, job)
                except Exception:
                    logger.exception(
                        "agent run job failed",
                        extra={"worker": worker_name, "job_id": str(job.job_id)},
                    )
                    await dispatch(
                        redis,
                        raw,
                        worker_name=worker_name,
                        results_queue=RESULTS_QUEUE,
                        dead_letter_queue=settings.agent_dead_letter_queue or DEAD_LETTER_QUEUE,
                    )
                continue

            await dispatch(
                redis,
                raw,
                worker_name=worker_name,
                results_queue=RESULTS_QUEUE,
                dead_letter_queue=settings.agent_dead_letter_queue or DEAD_LETTER_QUEUE,
            )
    finally:
        await redis.aclose()


async def run() -> None:
    settings = OrgWeaveSettings()
    configure_logging(settings.log_level)
    worker_name = os.environ.get("WORKER_NAME") or DEFAULT_WORKER_NAME
    started_at = datetime.now(UTC)
    stop_event = asyncio.Event()
    install_signal_handlers(stop_event)

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    redis = create_redis(settings)
    heartbeat_task = asyncio.create_task(
        heartbeat_loop(
            redis,
            worker_name,
            started_at,
            interval_seconds=settings.worker_heartbeat_interval_seconds,
            stop_event=stop_event,
            metadata={"queue": settings.agent_queue},
            ttl_seconds=max(int(settings.worker_heartbeat_interval_seconds * 6), 30),
        )
    )
    try:
        await consume_forever(
            settings,
            worker_name=worker_name,
            stop_event=stop_event,
            session_factory=session_factory,
        )
    finally:
        stop_event.set()
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        await write_heartbeat(redis, worker_name, started_at, status="stopped", ttl_seconds=10)
        await redis.aclose()
        await engine.dispose()
        logger.info("agent worker stopped", extra={"worker": worker_name})


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
