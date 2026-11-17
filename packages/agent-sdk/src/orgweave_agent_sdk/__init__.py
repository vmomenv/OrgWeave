"""Agent-facing contracts shared by the API and Agent Worker.

Phase 0 defines only the job envelope and tool descriptor. Agent sessions,
runs, memories and delegation contracts arrive in later phases.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class AgentJob(BaseModel):
    """A unit of work submitted to the Agent Worker queue."""

    job_id: UUID = Field(default_factory=uuid4)
    type: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    attempts: int = Field(default=0, ge=0)

    @field_validator("type")
    @classmethod
    def _type_is_namespaced(cls, value: str) -> str:
        if "." not in value:
            raise ValueError("job type must be namespaced, e.g. 'system.ping'")
        return value


class JobResult(BaseModel):
    job_id: UUID
    status: Literal["ok", "failed"]
    handled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    worker: str
    detail: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)


class AgentToolSpec(BaseModel):
    """Description of a tool an agent may be granted in a future phase."""

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(min_length=1)
    parameters_schema: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False
