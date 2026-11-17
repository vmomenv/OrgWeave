"""Pydantic response models for infrastructure endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "orgweave-api"
    version: str
    timestamp: datetime


class DependencyCheck(BaseModel):
    name: str
    status: Literal["ok", "error"]
    latency_ms: float = Field(ge=0)
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: Literal["ready", "degraded"]
    version: str
    timestamp: datetime
    checks: list[DependencyCheck]


class MetaResponse(BaseModel):
    name: str = "OrgWeave"
    api_version: str = "v1"
    phase: str = "0"
    version: str
    api_prefix: str = "/api/v1"
    ws_prefix: str = "/ws/v1"
    openapi_url: str = "/api/v1/openapi.json"
    docs_url: str = "/api/v1/docs"
