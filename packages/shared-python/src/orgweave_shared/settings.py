"""Environment-driven configuration shared by the API and all workers."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class OrgWeaveSettings(BaseSettings):
    """Single source of truth for service configuration.

    Values come from environment variables first and the repository ``.env``
    second. Container deployments inject the environment directly.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "development"
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000"

    database_url: str = (
        "postgresql+asyncpg://orgweave:orgweave_dev_password@localhost:5432/orgweave"
    )
    redis_url: str = "redis://localhost:6379/0"

    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "orgweave-phase0"

    litellm_base_url: str = "http://localhost:4000"
    litellm_master_key: str = "sk-orgweave-dev-master-key"
    default_model_alias: str = "orgweave-default"

    minio_endpoint: str = "localhost:9000"
    minio_secure: bool = False
    minio_bucket: str = "orgweave"
    s3_access_key: str = "orgweave"
    s3_secret_key: str = "orgweave_dev_minio_password"

    health_check_timeout_seconds: float = Field(default=3.0, gt=0, le=30)

    worker_name: str = "worker"
    worker_heartbeat_interval_seconds: float = Field(default=10.0, ge=1, le=300)
    watchdog_stale_after_seconds: float = Field(default=45.0, ge=5)
    watchdog_scan_interval_seconds: float = Field(default=15.0, ge=1)

    skill_runner_port: int = 8001
    agent_queue: str = "orgweave:agent:jobs"
    agent_dead_letter_queue: str = "orgweave:agent:dead-letter"

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg:// scheme")
        return value

    @field_validator("redis_url")
    @classmethod
    def _validate_redis_url(cls, value: str) -> str:
        if not value.startswith(("redis://", "rediss://")):
            raise ValueError("REDIS_URL must use redis:// or rediss://")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_development(self) -> bool:
        return self.app_env in {"development", "test"}


@lru_cache
def get_settings() -> OrgWeaveSettings:
    return OrgWeaveSettings()
