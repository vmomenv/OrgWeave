"""Skill Runner health service."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Literal

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from orgweave_shared import (
    OrgWeaveSettings,
    configure_logging,
    create_redis,
    heartbeat_loop,
    write_heartbeat,
)
from pydantic import BaseModel, Field

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


class RunTestsRequest(BaseModel):
    files: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=60, ge=5, le=120)


@app.post("/run-tests")
async def run_tests(request: Request, body: RunTestsRequest) -> JSONResponse:
    import subprocess
    import sys
    import tempfile
    import time
    from pathlib import Path

    if request.headers.get("x-internal-token") != settings.internal_service_token:
        return JSONResponse(status_code=401, content={"error": "unauthorized"})
    if not body.files:
        return JSONResponse(status_code=422, content={"error": "no_files"})
    if len(body.files) > 50:
        return JSONResponse(status_code=422, content={"error": "too_many_files"})
    total = sum(len(content.encode("utf-8")) for content in body.files.values())
    if total > 2 * 1024 * 1024:
        return JSONResponse(status_code=413, content={"error": "workspace_too_large"})

    tmp_root = Path(tempfile.mkdtemp(prefix="orgweave-tests-", dir="/tmp"))
    try:
        for relative, content in body.files.items():
            candidate = (tmp_root / relative).resolve()
            if not str(candidate).startswith(str(tmp_root.resolve()) + "/"):
                return JSONResponse(status_code=422, content={"error": "invalid_path"})
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_text(content, encoding="utf-8")

        started = time.perf_counter()
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                [
                    "/bin/sh",
                    "-c",
                    (
                        f"ulimit -t {body.timeout_seconds}; ulimit -v 524288; "
                        f"exec {sys.executable} -m pytest -q"
                    ),
                ],
                cwd=tmp_root,
                capture_output=True,
                text=True,
                timeout=body.timeout_seconds,
                env={"PATH": "/usr/local/bin:/usr/bin:/bin", "PYTHONPATH": str(tmp_root)},
            )
            exit_code = completed.returncode
            stdout = completed.stdout[-20000:]
            stderr = completed.stderr[-10000:]
        except subprocess.TimeoutExpired:
            exit_code = 124
            stdout = ""
            stderr = "test execution timed out"
        duration_ms = int((time.perf_counter() - started) * 1000)
        return JSONResponse(
            content={
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "duration_ms": duration_ms,
            }
        )
    finally:
        import shutil

        shutil.rmtree(tmp_root, ignore_errors=True)
