"""Agent configuration, sessions, runs, messages, tool calls and memory."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AgentConfig(Base):
    __tablename__ = "agent_configs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "member_id"],
            ["members.tenant_id", "members.id"],
            ondelete="CASCADE",
            name="fk_agent_member_same_tenant",
        ),
        UniqueConstraint("tenant_id", "member_id", name="uq_agent_tenant_member"),
        UniqueConstraint("tenant_id", "id", name="uq_agent_tenant_id_id"),
        CheckConstraint("max_steps BETWEEN 1 AND 100", name="ck_agent_max_steps"),
        Index("ix_agent_tenant", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    member_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    model_alias: Mapped[str] = mapped_column(
        String(120), nullable=False, default="orgweave-default"
    )
    temperature: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, default=0.2)
    max_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=1024)
    max_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    max_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    token_budget: Mapped[int] = mapped_column(Integer, nullable=False, default=50000)
    cost_budget_usd: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=5)
    max_tool_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    max_consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    allowed_tools: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    memory_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AgentSession(Base):
    __tablename__ = "agent_sessions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_session_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "agent_id"],
            ["agent_configs.tenant_id", "agent_configs.id"],
            ondelete="CASCADE",
            name="fk_session_agent_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "parent_session_id"],
            ["agent_sessions.tenant_id", "agent_sessions.id"],
            ondelete="RESTRICT",
            name="fk_session_parent_same_tenant",
        ),
        CheckConstraint(
            "status IN ('active','paused','completed','failed','killed','waiting_approval')",
            name="ck_session_status",
        ),
        CheckConstraint(
            "control_mode IN ('autonomous','guide','takeover')", name="ck_session_control"
        ),
        Index("ix_session_tenant_agent", "tenant_id", "agent_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    member_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    parent_session_id: Mapped[uuid.UUID | None] = mapped_column()
    task_id: Mapped[uuid.UUID | None] = mapped_column()
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    control_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="autonomous")
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="会话")
    context_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    model: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    token_usage: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_usage: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "session_id"],
            ["agent_sessions.tenant_id", "agent_sessions.id"],
            ondelete="CASCADE",
            name="fk_run_session_same_tenant",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_run_tenant_id_id"),
        CheckConstraint(
            "status IN ('queued','running','completed','failed','cancelled','timeout')",
            name="ck_run_status",
        ),
        Index("ix_run_tenant_session", "tenant_id", "session_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    input: Mapped[str] = mapped_column(Text, nullable=False)
    output: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    steps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_calls_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_usage: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_usage: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    limits: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentSessionMessage(Base):
    __tablename__ = "agent_session_messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "session_id"],
            ["agent_sessions.tenant_id", "agent_sessions.id"],
            ondelete="CASCADE",
            name="fk_session_message_session_same_tenant",
        ),
        CheckConstraint(
            "role IN ('system','user','assistant','tool')", name="ck_session_message_role"
        ),
        Index("ix_session_message_session", "tenant_id", "session_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tool_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    tool_call_id: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AgentToolCall(Base):
    __tablename__ = "agent_tool_calls"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            ondelete="CASCADE",
            name="fk_tool_call_run_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "session_id"],
            ["agent_sessions.tenant_id", "agent_sessions.id"],
            ondelete="CASCADE",
            name="fk_tool_call_session_same_tenant",
        ),
        CheckConstraint(
            "status IN ('requested','running','completed','failed','denied')",
            name="ck_tool_call_status",
        ),
        Index("ix_tool_call_run", "tenant_id", "run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    tool_call_id: Mapped[str] = mapped_column(String(120), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    arguments: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="requested")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentMemory(Base):
    __tablename__ = "agent_memories"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "agent_id"],
            ["agent_configs.tenant_id", "agent_configs.id"],
            ondelete="CASCADE",
            name="fk_memory_agent_same_tenant",
        ),
        CheckConstraint(
            "memory_type IN ('profile','semantic','episodic','task','procedural')",
            name="ck_memory_type",
        ),
        CheckConstraint("importance BETWEEN 1 AND 5", name="ck_memory_importance"),
        Index("ix_memory_tenant_agent", "tenant_id", "agent_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    memory_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    source_session_id: Mapped[uuid.UUID | None] = mapped_column()
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
