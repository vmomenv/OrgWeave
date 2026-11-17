"""Agent config, session, run and memory schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

MEMORY_TYPES = ("profile", "semantic", "episodic", "task", "procedural")


class AgentCreate(BaseModel):
    member_id: uuid.UUID
    system_prompt: str = Field(default="", max_length=8000)
    model_alias: str = Field(default="orgweave-default", min_length=1, max_length=120)
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_output_tokens: int = Field(default=1024, ge=64, le=8192)
    max_steps: int = Field(default=8, ge=1, le=100)
    max_duration_seconds: int = Field(default=300, ge=10, le=3600)
    token_budget: int = Field(default=50000, ge=100, le=10_000_000)
    cost_budget_usd: float = Field(default=5, ge=0, le=10000)
    max_tool_calls: int = Field(default=20, ge=0, le=200)
    max_consecutive_failures: int = Field(default=3, ge=1, le=20)
    allowed_tools: list[str] = Field(
        default_factory=lambda: [
            "get_current_time",
            "list_team_members",
            "remember",
            "search_memory",
        ]
    )
    memory_enabled: bool = True


class AgentUpdate(BaseModel):
    system_prompt: str | None = Field(default=None, max_length=8000)
    model_alias: str | None = Field(default=None, min_length=1, max_length=120)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_output_tokens: int | None = Field(default=None, ge=64, le=8192)
    max_steps: int | None = Field(default=None, ge=1, le=100)
    max_duration_seconds: int | None = Field(default=None, ge=10, le=3600)
    token_budget: int | None = Field(default=None, ge=100, le=10_000_000)
    cost_budget_usd: float | None = Field(default=None, ge=0, le=10000)
    max_tool_calls: int | None = Field(default=None, ge=0, le=200)
    max_consecutive_failures: int | None = Field(default=None, ge=1, le=20)
    allowed_tools: list[str] | None = None
    memory_enabled: bool | None = None


class AgentOut(BaseModel):
    id: uuid.UUID
    member_id: uuid.UUID
    member_name: str
    member_title: str | None
    member_ai_enabled: bool
    system_prompt: str
    model_alias: str
    temperature: float
    max_output_tokens: int
    max_steps: int
    max_duration_seconds: int
    token_budget: int
    cost_budget_usd: float
    max_tool_calls: int
    max_consecutive_failures: int
    allowed_tools: list[str]
    memory_enabled: bool
    created_at: datetime
    updated_at: datetime


class SessionCreate(BaseModel):
    title: str = Field(default="新会话", min_length=1, max_length=200)


class SessionOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    member_id: uuid.UUID
    parent_session_id: uuid.UUID | None
    status: str
    control_mode: str
    title: str
    context_summary: str
    model: str
    token_usage: int
    cost_usage: float
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    last_run_status: str | None = None


class RunLimits(BaseModel):
    max_steps: int | None = Field(default=None, ge=1, le=100)
    max_duration_seconds: int | None = Field(default=None, ge=10, le=3600)
    token_budget: int | None = Field(default=None, ge=100, le=10_000_000)
    max_tool_calls: int | None = Field(default=None, ge=0, le=200)
    max_consecutive_failures: int | None = Field(default=None, ge=1, le=20)

    @model_validator(mode="after")
    def _at_least_one(self) -> RunLimits:
        return self


class RunCreate(BaseModel):
    input: str = Field(min_length=1, max_length=20000)
    limits: RunLimits | None = None


class RunOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    status: str
    input: str
    output: str | None
    error: str | None
    steps: int
    tool_calls_count: int
    token_usage: int
    cost_usage: float
    limits: dict[str, Any]
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class SessionMessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    tool_calls: list[dict[str, Any]] | None
    tool_call_id: str | None
    created_at: datetime


class ToolCallOut(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    tool_name: str
    arguments: dict[str, Any]
    result: dict[str, Any] | None
    status: str
    error: str | None
    created_at: datetime
    completed_at: datetime | None


class MemoryCreate(BaseModel):
    memory_type: Literal["profile", "semantic", "episodic", "task", "procedural"] = "semantic"
    content: str = Field(min_length=1, max_length=4000)
    importance: int = Field(default=3, ge=1, le=5)


class MemoryOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    memory_type: str
    content: str
    importance: int
    source_session_id: uuid.UUID | None
    metadata: dict[str, Any]
    created_at: datetime
