"""Job dispatch semantics for the Agent Worker."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from orgweave_agent_sdk import AgentJob, JobResult
from pydantic import ValidationError
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

SUPPORTED_JOB_TYPES = frozenset({"system.ping"})
RESULTS_QUEUE = "orgweave:agent:results"
DEAD_LETTER_QUEUE = "orgweave:agent:dead-letter"
DEAD_LETTER_LIMIT = 1000


class UnsupportedJobType(Exception):
    def __init__(self, job_type: str) -> None:
        super().__init__(f"unsupported job type: {job_type}")
        self.job_type = job_type


def process_job(job: AgentJob) -> dict[str, Any]:
    """Execute a Phase 0 job synchronously and deterministically."""
    if job.type not in SUPPORTED_JOB_TYPES:
        raise UnsupportedJobType(job.type)
    return {"pong": True, "echo": job.payload, "job_type": job.type}


async def dead_letter(
    redis: Redis,
    raw: str,
    reason: str,
    *,
    queue: str = DEAD_LETTER_QUEUE,
) -> None:
    payload = {
        "reason": reason,
        "received_at": datetime.now(UTC).isoformat(),
        "raw": raw[:2000],
    }
    await redis.rpush(queue, json.dumps(payload, ensure_ascii=False))
    await redis.ltrim(queue, -DEAD_LETTER_LIMIT, -1)
    logger.warning("job dead-lettered: %s", reason)


async def dispatch(
    redis: Redis,
    raw: str,
    *,
    worker_name: str,
    results_queue: str = RESULTS_QUEUE,
    dead_letter_queue: str = DEAD_LETTER_QUEUE,
) -> JobResult | None:
    """Parse, execute and acknowledge one raw job payload.

    Invalid and unsupported jobs return ``None`` after being dead-lettered. A
    successful job produces a ``JobResult`` appended to the results queue.
    """
    try:
        job = AgentJob.model_validate_json(raw)
    except ValidationError as exc:
        await dead_letter(
            redis, raw, f"invalid_job_envelope: {exc.error_count()} errors", queue=dead_letter_queue
        )
        return None

    try:
        result_payload = process_job(job)
    except UnsupportedJobType as exc:
        await dead_letter(redis, raw, str(exc), queue=dead_letter_queue)
        return None

    result = JobResult(
        job_id=job.job_id,
        status="ok",
        worker=worker_name,
        result=result_payload,
    )
    await redis.rpush(results_queue, result.model_dump_json())
    logger.info("job completed", extra={"worker": worker_name, "job_id": str(job.job_id)})
    return result
