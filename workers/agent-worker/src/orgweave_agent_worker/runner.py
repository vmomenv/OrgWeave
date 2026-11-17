"""Agent Runtime job adapter for the Agent Worker."""

from __future__ import annotations

import logging
import uuid

from app.application.agent_runtime import execute_run
from orgweave_agent_sdk import AgentJob
from orgweave_shared import OrgWeaveSettings
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

logger = logging.getLogger("orgweave.agent_worker.runner")


async def handle_agent_run(
    redis: Redis,
    settings: OrgWeaveSettings,
    session_factory: async_sessionmaker,
    job: AgentJob,
) -> None:
    run_id = uuid.UUID(str(job.payload["run_id"]))
    tenant_id = uuid.UUID(str(job.payload["tenant_id"]))
    async with session_factory() as session:
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )
        await execute_run(session, redis, settings, run_id, session_factory=session_factory)
    logger.info(
        "agent run processed",
        extra={"worker": settings.worker_name, "task_id": str(run_id)},
    )
