"""Dependency health probes.

Probes are deliberately small and deterministic. They answer "can the API talk
to the real dependency right now?", never "is the dependency configured".
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from minio import Minio
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import OrgWeaveSettings
from app.schemas.health import DependencyCheck

_CREDENTIAL_RE = re.compile(r"(?P<scheme>[a-z][a-z0-9+.-]*://)[^@\s]+@")


@dataclass(frozen=True)
class Probe:
    name: str
    check: Callable[[], Awaitable[DependencyCheck]]


def safe_error(exc: BaseException) -> str:
    """Format an exception without leaking credentials embedded in URLs."""
    message = _CREDENTIAL_RE.sub(r"\g<scheme>***@", str(exc) or exc.__class__.__name__)
    if len(message) > 300:
        message = message[:297] + "..."
    return f"{exc.__class__.__name__}: {message}"


async def _check_postgres(engine: AsyncEngine) -> DependencyCheck:
    started = asyncio.get_running_loop().time()
    async with engine.connect() as connection:
        row = (
            (
                await connection.execute(
                    text(
                        """
                    SELECT current_database() AS database,
                           current_setting('server_version') AS server_version,
                           EXISTS (
                               SELECT 1 FROM pg_extension WHERE extname = 'vector'
                           ) AS has_vector,
                           (
                               SELECT extversion FROM pg_extension WHERE extname = 'vector'
                           ) AS vector_version
                    """
                    )
                )
            )
            .mappings()
            .one()
        )
    latency = (asyncio.get_running_loop().time() - started) * 1000
    if not row["has_vector"]:
        return DependencyCheck(
            name="postgres",
            status="error",
            latency_ms=round(latency, 2),
            detail=f"database={row['database']} pg={row['server_version']} pgvector=missing",
        )
    return DependencyCheck(
        name="postgres",
        status="ok",
        latency_ms=round(latency, 2),
        detail=(
            f"database={row['database']} pg={row['server_version']} "
            f"pgvector={row['vector_version']}"
        ),
    )


async def _check_redis(client: Redis) -> DependencyCheck:
    started = asyncio.get_running_loop().time()
    reply = await client.ping()
    latency = (asyncio.get_running_loop().time() - started) * 1000
    return DependencyCheck(
        name="redis",
        status="ok" if reply else "error",
        latency_ms=round(latency, 2),
        detail="ping=ok" if reply else "ping=unexpected-reply",
    )


async def _check_minio(client: Minio, bucket: str) -> DependencyCheck:
    started = asyncio.get_running_loop().time()
    exists = await asyncio.to_thread(client.bucket_exists, bucket)
    latency = (asyncio.get_running_loop().time() - started) * 1000
    return DependencyCheck(
        name="minio",
        status="ok" if exists else "error",
        latency_ms=round(latency, 2),
        detail=f"bucket={bucket} present={str(exists).lower()}",
    )


async def _check_temporal(settings: OrgWeaveSettings) -> DependencyCheck:
    from datetime import timedelta

    from temporalio.api.workflowservice.v1 import GetSystemInfoRequest
    from temporalio.client import Client

    started = asyncio.get_running_loop().time()
    client = await Client.connect(
        settings.temporal_host,
        namespace=settings.temporal_namespace,
        connect_timeout=timedelta(seconds=settings.health_check_timeout_seconds),
    )
    info = await client.workflow_service.get_system_info(GetSystemInfoRequest())
    latency = (asyncio.get_running_loop().time() - started) * 1000
    return DependencyCheck(
        name="temporal",
        status="ok",
        latency_ms=round(latency, 2),
        detail=f"host={settings.temporal_host} server={info.server_version}",
    )


async def _check_litellm(settings: OrgWeaveSettings) -> DependencyCheck:
    import httpx

    started = asyncio.get_running_loop().time()
    headers = {}
    if settings.litellm_master_key:
        headers["Authorization"] = f"Bearer {settings.litellm_master_key}"
    async with httpx.AsyncClient(
        base_url=settings.litellm_base_url.rstrip("/"),
        timeout=settings.health_check_timeout_seconds,
        headers=headers,
    ) as client:
        response = await client.get("/health/liveliness")
    latency = (asyncio.get_running_loop().time() - started) * 1000
    ok = response.status_code == 200
    return DependencyCheck(
        name="litellm",
        status="ok" if ok else "error",
        latency_ms=round(latency, 2),
        detail=f"http={response.status_code}",
    )


def build_probes(
    settings: OrgWeaveSettings,
    *,
    engine: AsyncEngine,
    redis_client: Redis,
    minio_client: Minio,
) -> list[Probe]:
    return [
        Probe("postgres", lambda: _check_postgres(engine)),
        Probe("redis", lambda: _check_redis(redis_client)),
        Probe("minio", lambda: _check_minio(minio_client, settings.minio_bucket)),
        Probe("temporal", lambda: _check_temporal(settings)),
        Probe("litellm", lambda: _check_litellm(settings)),
    ]
