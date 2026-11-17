"""Skill Runner health service."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Literal

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from orgweave_shared import (
    OrgWeaveSettings,
    configure_logging,
    create_redis,
    heartbeat_loop,
    write_heartbeat,
)

settings = OrgWeaveSettings()
DEFAULT_WORKER_NAME = "skill-runner"
worker_name = os.environ.get("WORKER_NAME") or DEFAULT_WORKER_NAME


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    redis = create_redis(settings)
    stop_event = asyncio.Event()
    started_at = datetime.now(UTC)
    heartbeat_task = asyncio.create_task(
        heartbeat_loop(
            redis,
            worker_name,
            started_at,
            interval_seconds=settings.worker_heartbeat_interval_seconds,
            stop_event=stop_event,
            metadata={"service": "skill-runner"},
            ttl_seconds=max(int(settings.worker_heartbeat_interval_seconds * 6), 30),
        )
    )
    app.state.redis = redis
    app.state.started_at = started_at
    try:
        yield
    finally:
        stop_event.set()
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        await write_heartbeat(redis, worker_name, started_at, status="stopped", ttl_seconds=10)
        await redis.aclose()


app = FastAPI(
    title="OrgWeave Skill Runner",
    version=settings.app_version,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.get("/health/live")
async def live() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "orgweave-skill-runner",
        "version": settings.app_version,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@app.get("/health/ready")
async def ready() -> JSONResponse:
    redis = app.state.redis
    status: Literal["ready", "degraded"] = "ready"
    detail = "ping=ok"
    try:
        async with asyncio.timeout(settings.health_check_timeout_seconds):
            await redis.ping()
    except Exception as exc:
        status = "degraded"
        detail = f"redis_error={exc.__class__.__name__}"
    return JSONResponse(
        status_code=200 if status == "ready" else 503,
        content={
            "status": status,
            "service": "orgweave-skill-runner",
            "detail": detail,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


def main() -> None:
    uvicorn.run(
        "orgweave_skill_runner.main:app",
        host="0.0.0.0",
        port=settings.skill_runner_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
