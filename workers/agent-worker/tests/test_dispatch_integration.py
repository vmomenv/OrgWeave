"""Dispatch tests against a real Redis instance."""

from __future__ import annotations

import json

import pytest
from orgweave_agent_sdk import AgentJob
from orgweave_agent_worker.jobs import dispatch
from orgweave_shared import OrgWeaveSettings, create_redis

pytestmark = pytest.mark.integration


@pytest.fixture
async def redis():
    client = create_redis(OrgWeaveSettings())
    yield client
    await client.aclose()


async def test_valid_job_is_processed_and_result_queued(redis) -> None:
    results_queue = "orgweave:test:agent:results"
    dead_queue = "orgweave:test:agent:dead"
    await redis.delete(results_queue, dead_queue)
    job = AgentJob(type="system.ping", payload={"n": 1})

    result = await dispatch(
        redis,
        job.model_dump_json(),
        worker_name="agent-worker",
        results_queue=results_queue,
        dead_letter_queue=dead_queue,
    )

    assert result is not None
    assert result.status == "ok"
    queued = json.loads(await redis.lindex(results_queue, 0))
    assert queued["job_id"] == str(job.job_id)
    assert queued["result"]["echo"] == {"n": 1}
    assert await redis.llen(dead_queue) == 0
    await redis.delete(results_queue)


async def test_invalid_and_unsupported_jobs_are_dead_lettered(redis) -> None:
    results_queue = "orgweave:test:agent:results"
    dead_queue = "orgweave:test:agent:dead"
    await redis.delete(results_queue, dead_queue)

    assert (
        await dispatch(
            redis,
            "{not-json",
            worker_name="agent-worker",
            results_queue=results_queue,
            dead_letter_queue=dead_queue,
        )
        is None
    )
    assert (
        await dispatch(
            redis,
            AgentJob(type="system.unsupported").model_dump_json(),
            worker_name="agent-worker",
            results_queue=results_queue,
            dead_letter_queue=dead_queue,
        )
        is None
    )

    assert await redis.llen(results_queue) == 0
    assert await redis.llen(dead_queue) == 2
    reasons = [json.loads(item)["reason"] for item in await redis.lrange(dead_queue, 0, -1)]
    assert any(reason.startswith("invalid_job_envelope") for reason in reasons)
    assert any("unsupported job type" in reason for reason in reasons)
    await redis.delete(dead_queue)
