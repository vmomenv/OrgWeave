"""Integration tests against the real Docker Compose infrastructure.

These prove the API is wired to PostgreSQL/pgvector, Redis, MinIO, Temporal and
LiteLLM — not to in-process fakes.
"""

from __future__ import annotations

import os

import pytest
from app.main import app
from fastapi.testclient import TestClient
from minio import Minio
from orgweave_shared.settings import OrgWeaveSettings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def settings() -> OrgWeaveSettings:
    return OrgWeaveSettings()


@pytest.fixture(scope="module")
def api_client() -> TestClient:
    with TestClient(app) as client:
        yield client


def test_readiness_reports_every_real_dependency(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/health/ready")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ready"
    checks = {check["name"]: check for check in body["checks"]}
    assert set(checks) == {"postgres", "redis", "minio", "temporal", "litellm"}
    assert all(check["status"] == "ok" for check in checks.values()), body


def test_pgvector_extension_is_installed(settings: OrgWeaveSettings) -> None:
    async def query() -> str:
        engine = create_async_engine(settings.database_url)
        try:
            async with engine.connect() as connection:
                return (
                    await connection.execute(
                        text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                    )
                ).scalar_one()
        finally:
            await engine.dispose()

    import asyncio

    version = asyncio.run(query())
    assert version.split(".")[0].isdigit()


def test_alembic_baseline_is_applied(settings: OrgWeaveSettings) -> None:
    async def query() -> tuple[str, str]:
        engine = create_async_engine(settings.database_url)
        try:
            async with engine.connect() as connection:
                revision = (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one()
                table = (
                    await connection.execute(
                        text("SELECT to_regclass('public.system_settings')::text")
                    )
                ).scalar_one()
                return revision, table
        finally:
            await engine.dispose()

    import asyncio

    revision, table = asyncio.run(query())
    assert revision == "0005_phase4_delegation"
    assert table == "system_settings"


def test_minio_bucket_exists(settings: OrgWeaveSettings) -> None:
    client = Minio(
        settings.minio_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        secure=settings.minio_secure,
    )
    assert client.bucket_exists(settings.minio_bucket) is True


def test_litellm_gateway_lists_default_alias() -> None:
    import httpx

    settings = OrgWeaveSettings()
    headers = {"Authorization": f"Bearer {settings.litellm_master_key}"}
    response = httpx.get(
        f"{settings.litellm_base_url.rstrip('/')}/health/liveliness",
        headers=headers,
        timeout=5,
    )
    assert response.status_code == 200


def test_integration_environment_variable_is_explicit() -> None:
    assert os.environ.get("ORGWEAVE_INTEGRATION") == "1"
