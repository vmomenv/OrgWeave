"""MinIO object storage bootstrap."""

from __future__ import annotations

import asyncio

from minio import Minio

from app.core.config import OrgWeaveSettings


def create_minio_client(settings: OrgWeaveSettings) -> Minio:
    return Minio(
        settings.minio_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        secure=settings.minio_secure,
    )


async def ensure_bucket(
    client: Minio,
    bucket: str,
    *,
    timeout_seconds: float,
) -> bool:
    """Create the bucket if missing. Returns True when it exists afterwards.

    Bucket creation is idempotent so restarts and multiple API replicas are safe.
    """
    return await asyncio.wait_for(
        asyncio.to_thread(_ensure_bucket_sync, client, bucket),
        timeout=timeout_seconds,
    )


def _ensure_bucket_sync(client: Minio, bucket: str) -> bool:
    if client.bucket_exists(bucket):
        return True
    client.make_bucket(bucket)
    return client.bucket_exists(bucket)
