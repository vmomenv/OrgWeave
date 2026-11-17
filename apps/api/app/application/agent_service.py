"""Agent configuration, session, run and memory services."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.agent_runtime import build_limits
from app.application.tools import DEFAULT_TOOLS, TOOL_SCHEMAS
from app.core.config import OrgWeaveSettings
from app.core.errors import ApiError
from app.models import (
    AgentConfig,
    AgentRun,
    AgentSession,
    AgentSessionMessage,
    AgentToolCall,
    Member,
)
from app.schemas.agent import AgentCreate, AgentOut, AgentUpdate, RunOut, SessionOut


def validate_tools(tools: list[str]) -> list[str]:
    unknown = [name for name in tools if name not in TOOL_SCHEMAS]
    if unknown:
        raise ApiError(422, "unknown_tools", "存在未受支持的工具", details={"tools": unknown})
    return list(dict.fromkeys(tools))


def serialize_agent(agent: AgentConfig, member: Member) -> AgentOut:
    return AgentOut(
        id=agent.id,
        member_id=member.id,
        member_name=member.display_name,
        member_title=member.title,
        member_ai_enabled=member.ai_enabled,
        system_prompt=agent.system_prompt,
        model_alias=agent.model_alias,
        temperature=float(agent.temperature),
        max_output_tokens=agent.max_output_tokens,
        max_steps=agent.max_steps,
        max_duration_seconds=agent.max_duration_seconds,
        token_budget=agent.token_budget,
        cost_budget_usd=float(agent.cost_budget_usd),
        max_tool_calls=agent.max_tool_calls,
        max_consecutive_failures=agent.max_consecutive_failures,
        max_delegation_depth=agent.max_delegation_depth,
        allowed_agent_ids=agent.allowed_agent_ids,
        allowed_tools=agent.allowed_tools,
        memory_enabled=agent.memory_enabled,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


async def ensure_agent_for_member(
    session: AsyncSession, tenant_id: uuid.UUID, member: Member
) -> AgentConfig | None:
    if member.member_type != "ai":
        return None
    existing = await session.scalar(
        select(AgentConfig).where(
            AgentConfig.tenant_id == tenant_id, AgentConfig.member_id == member.id
        )
    )
    if existing is not None:
        return existing
    agent = AgentConfig(
        tenant_id=tenant_id,
        member_id=member.id,
        system_prompt="",
        model_alias=OrgWeaveSettings().default_model_alias,
        allowed_tools=list(DEFAULT_TOOLS),
    )
    session.add(agent)
    await session.flush()
    return agent


async def get_agent(
    session: AsyncSession, tenant_id: uuid.UUID, agent_id: uuid.UUID
) -> AgentConfig:
    agent = await session.scalar(
        select(AgentConfig).where(AgentConfig.tenant_id == tenant_id, AgentConfig.id == agent_id)
    )
    if agent is None:
        raise ApiError(404, "agent_not_found", "AI 员工配置不存在")
    return agent


async def create_agent(
    session: AsyncSession, tenant_id: uuid.UUID, body: AgentCreate
) -> AgentConfig:
    member = await session.scalar(
        select(Member).where(
            Member.tenant_id == tenant_id,
            Member.id == body.member_id,
            Member.member_type == "ai",
        )
    )
    if member is None:
        raise ApiError(422, "invalid_ai_member", "必须关联本租户的 AI 成员")
    existing = await session.scalar(
        select(AgentConfig.id).where(
            AgentConfig.tenant_id == tenant_id, AgentConfig.member_id == member.id
        )
    )
    if existing is not None:
        raise ApiError(409, "agent_exists", "该 AI 成员已有配置")
    agent = AgentConfig(
        tenant_id=tenant_id,
        member_id=member.id,
        system_prompt=body.system_prompt,
        model_alias=body.model_alias,
        temperature=body.temperature,
        max_output_tokens=body.max_output_tokens,
        max_steps=body.max_steps,
        max_duration_seconds=body.max_duration_seconds,
        token_budget=body.token_budget,
        cost_budget_usd=body.cost_budget_usd,
        max_tool_calls=body.max_tool_calls,
        max_consecutive_failures=body.max_consecutive_failures,
        max_delegation_depth=body.max_delegation_depth,
        allowed_agent_ids=body.allowed_agent_ids,
        allowed_tools=validate_tools(body.allowed_tools),
        memory_enabled=body.memory_enabled,
    )
    session.add(agent)
    await session.flush()
    return agent


async def update_agent(session: AsyncSession, agent: AgentConfig, body: AgentUpdate) -> AgentConfig:
    fields = body.model_fields_set
    for field in (
        "system_prompt",
        "model_alias",
        "temperature",
        "max_output_tokens",
        "max_steps",
        "max_duration_seconds",
        "token_budget",
        "cost_budget_usd",
        "max_tool_calls",
        "max_consecutive_failures",
        "max_delegation_depth",
        "memory_enabled",
    ):
        if field in fields:
            value = getattr(body, field)
            if value is not None:
                setattr(agent, field, value)
    if "allowed_tools" in fields and body.allowed_tools is not None:
        agent.allowed_tools = validate_tools(body.allowed_tools)
    if "allowed_agent_ids" in fields and body.allowed_agent_ids is not None:
        agent.allowed_agent_ids = body.allowed_agent_ids
    await session.flush()
    return agent


async def create_session(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    agent: AgentConfig,
    *,
    title: str,
) -> AgentSession:
    agent_session = AgentSession(
        tenant_id=tenant_id,
        agent_id=agent.id,
        member_id=agent.member_id,
        title=title.strip(),
        model=agent.model_alias,
        status="active",
        control_mode="autonomous",
    )
    session.add(agent_session)
    await session.flush()
    return agent_session


async def session_out(session: AsyncSession, agent_session: AgentSession) -> SessionOut:
    last_run = await session.scalar(
        select(AgentRun)
        .where(
            AgentRun.tenant_id == agent_session.tenant_id,
            AgentRun.session_id == agent_session.id,
        )
        .order_by(AgentRun.created_at.desc())
        .limit(1)
    )
    return SessionOut(
        id=agent_session.id,
        agent_id=agent_session.agent_id,
        member_id=agent_session.member_id,
        parent_session_id=agent_session.parent_session_id,
        status=agent_session.status,
        control_mode=agent_session.control_mode,
        title=agent_session.title,
        context_summary=agent_session.context_summary,
        model=agent_session.model,
        token_usage=agent_session.token_usage,
        cost_usage=float(agent_session.cost_usage),
        created_at=agent_session.created_at,
        updated_at=agent_session.updated_at,
        started_at=agent_session.started_at,
        completed_at=agent_session.completed_at,
        last_run_status=last_run.status if last_run else None,
    )


async def create_run(
    session: AsyncSession,
    agent_session: AgentSession,
    agent: AgentConfig,
    *,
    input_text: str,
    limits: dict[str, Any] | None,
) -> AgentRun:
    run = AgentRun(
        tenant_id=agent_session.tenant_id,
        session_id=agent_session.id,
        status="queued",
        input=input_text,
        limits=build_limits(agent, limits),
    )
    session.add(run)
    await session.flush()
    return run


async def cancel_run(session: AsyncSession, tenant_id: uuid.UUID, run: AgentRun) -> None:
    if run.status == "queued":
        run.status = "cancelled"
        run.error = "cancelled_by_user"
        run.completed_at = datetime.now(UTC)
    else:
        # Running workers observe this key before the next model/tool call.
        pass
    await session.flush()


def run_out(run: AgentRun) -> RunOut:
    return RunOut(
        id=run.id,
        session_id=run.session_id,
        status=run.status,
        input=run.input,
        output=run.output,
        error=run.error,
        steps=run.steps,
        tool_calls_count=run.tool_calls_count,
        token_usage=run.token_usage,
        cost_usage=float(run.cost_usage),
        limits=run.limits,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


async def get_run(session: AsyncSession, tenant_id: uuid.UUID, run_id: uuid.UUID) -> AgentRun:
    run = await session.scalar(
        select(AgentRun).where(AgentRun.tenant_id == tenant_id, AgentRun.id == run_id)
    )
    if run is None:
        raise ApiError(404, "run_not_found", "执行记录不存在")
    return run


async def get_session(
    session: AsyncSession, tenant_id: uuid.UUID, session_id: uuid.UUID
) -> AgentSession:
    agent_session = await session.scalar(
        select(AgentSession).where(
            AgentSession.tenant_id == tenant_id, AgentSession.id == session_id
        )
    )
    if agent_session is None:
        raise ApiError(404, "session_not_found", "会话不存在")
    return agent_session


async def list_session_messages(
    session: AsyncSession, tenant_id: uuid.UUID, session_id: uuid.UUID
) -> list[AgentSessionMessage]:
    return list(
        (
            await session.scalars(
                select(AgentSessionMessage)
                .where(
                    AgentSessionMessage.tenant_id == tenant_id,
                    AgentSessionMessage.session_id == session_id,
                )
                .order_by(AgentSessionMessage.created_at)
            )
        ).all()
    )


async def list_tool_calls(
    session: AsyncSession, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> list[AgentToolCall]:
    return list(
        (
            await session.scalars(
                select(AgentToolCall)
                .where(AgentToolCall.tenant_id == tenant_id, AgentToolCall.run_id == run_id)
                .order_by(AgentToolCall.created_at)
            )
        ).all()
    )
