"""Redis client helpers with bounded connection and socket timeouts."""

from __future__ import annotations

from redis.asyncio import Redis

from orgweave_shared.settings import OrgWeaveSettings


def create_redis(settings: OrgWeaveSettings) -> Redis:
    """Create an async Redis client.

    Timeouts are mandatory: health checks and worker loops must never hang on a
    half-open TCP connection.
    """
    timeout = settings.health_check_timeout_seconds
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=timeout,
        socket_timeout=timeout,
        health_check_interval=30,
    )


async def check_redis(client: Redis) -> None:
    """Raise if Redis does not answer PING."""
    await client.ping()
