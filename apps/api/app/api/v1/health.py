"""Health endpoints: liveness is process-only, readiness checks real dependencies."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import get_health_probes
from app.core.config import get_settings
from app.infrastructure.health.probes import Probe, safe_error
from app.schemas.health import DependencyCheck, LivenessResponse, ReadinessResponse

router = APIRouter(prefix="/health", tags=["health"])


async def run_probe(probe: Probe, timeout_seconds: float) -> DependencyCheck:
    started = time.perf_counter()
    try:
        async with asyncio.timeout(timeout_seconds):
            return await probe.check()
    except TimeoutError:
        return DependencyCheck(
            name=probe.name,
            status="error",
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            detail=f"timed out after {timeout_seconds}s",
        )
    except Exception as exc:
        return DependencyCheck(
            name=probe.name,
            status="error",
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            detail=safe_error(exc),
        )


@router.get("/live", response_model=LivenessResponse, summary="Process liveness")
async def liveness() -> LivenessResponse:
    settings = get_settings()
    return LivenessResponse(version=settings.app_version, timestamp=datetime.now(UTC))


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Dependency readiness",
    responses={503: {"model": ReadinessResponse, "description": "A dependency is down"}},
)
async def readiness(
    response: Response,
    probes: Annotated[list[Probe], Depends(get_health_probes)],
) -> ReadinessResponse:
    settings = get_settings()
    checks = await asyncio.gather(
        *(run_probe(probe, settings.health_check_timeout_seconds) for probe in probes)
    )
    ready = all(check.status == "ok" for check in checks)
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if ready else "degraded",
        version=settings.app_version,
        timestamp=datetime.now(UTC),
        checks=list(checks),
    )
