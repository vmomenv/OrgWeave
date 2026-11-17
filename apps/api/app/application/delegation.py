"""Agent delegation: authorization, child sessions and result propagation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.models import (
    AgentConfig,
    AgentDelegation,
    AgentRun,
    AgentSession,
    AgentSessionMessage,
    Member,
)


async def available_agents(
    session: AsyncSession, tenant_id: uuid.UUID, parent_agent: AgentConfig
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(AgentConfig, Member)
            .join(
                Member,
                (Member.id == AgentConfig.member_id) & (Member.tenant_id == AgentConfig.tenant_id),
            )
            .where(
                AgentConfig.tenant_id == tenant_id,
                AgentConfig.id != parent_agent.id,
                Member.member_type == "ai",
                Member.status == "active",
            )
            .order_by(Member.display_name)
        )
    ).all()
    allowed = set(parent_agent.allowed_agent_ids or [])
    permit_all = "*" in allowed
    return [
        {
            "agent_id": str(agent.id),
            "name": member.display_name,
            "title": member.title,
            "ai_enabled": member.ai_enabled,
        }
        for agent, member in rows
        if permit_all or str(agent.id) in allowed
    ]


async def resolve_target(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    parent_agent: AgentConfig,
    *,
    agent_id: str | None,
    agent_name: str | None,
) -> tuple[AgentConfig, Member]:
    statement = (
        select(AgentConfig, Member)
        .join(
            Member,
            (Member.id == AgentConfig.member_id) & (Member.tenant_id == AgentConfig.tenant_id),
        )
        .where(AgentConfig.tenant_id == tenant_id, Member.member_type == "ai")
    )
    if agent_id:
        statement = statement.where(AgentConfig.id == uuid.UUID(agent_id))
    elif agent_name:
        statement = statement.where(Member.display_name.ilike(agent_name.strip()))
    else:
        raise ApiError(422, "agent_required", "必须指定目标 Agent")
    row = (await session.execute(statement)).first()
    if row is None:
        raise ApiError(404, "delegate_agent_not_found", "目标 AI 员工不存在")
    target_agent, target_member = row

    allowed = set(parent_agent.allowed_agent_ids or [])
    if "*" not in allowed and str(target_agent.id) not in allowed:
        raise ApiError(403, "delegation_denied", "当前 Agent 无权委派给该员工")
    if target_agent.id == parent_agent.id:
        raise ApiError(422, "delegation_self", "Agent 不能委派给自己")
    if target_member.status != "active":
        raise ApiError(422, "delegate_inactive", "目标 AI 员工已停用")
    if not target_member.ai_enabled:
        raise ApiError(422, "delegate_ai_disabled", "目标 AI 员工的 AI 能力已关闭")
    return target_agent, target_member


async def session_depth(session: AsyncSession, tenant_id: uuid.UUID, session_id: uuid.UUID) -> int:
    value = await session.scalar(
        text(
            """
            WITH RECURSIVE ancestry AS (
                SELECT id, parent_session_id, 0 AS depth
                FROM agent_sessions
                WHERE tenant_id = :tenant_id AND id = :session_id
                UNION ALL
                SELECT s.id, s.parent_session_id, a.depth + 1
                FROM agent_sessions s
                JOIN ancestry a ON s.id = a.parent_session_id
                WHERE s.tenant_id = :tenant_id
            )
            SELECT COALESCE(max(depth), 0) FROM ancestry
            """
        ),
        {"tenant_id": str(tenant_id), "session_id": str(session_id)},
    )
    return int(value or 0)


async def create_delegation(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    parent_run: AgentRun,
    parent_session: AgentSession,
    parent_agent: AgentConfig,
    target_agent: AgentConfig,
    target_member: Member,
    task: str,
) -> AgentDelegation:
    from app.application.agent_runtime import build_limits

    depth = await session_depth(session, tenant_id, parent_session.id)
    if depth >= parent_agent.max_delegation_depth:
        raise ApiError(
            409,
            "delegation_depth_exceeded",
            f"委派层级超过限制（max={parent_agent.max_delegation_depth}）",
        )

    child_session = AgentSession(
        tenant_id=tenant_id,
        agent_id=target_agent.id,
        member_id=target_agent.member_id,
        parent_session_id=parent_session.id,
        status="active",
        control_mode="autonomous",
        title=f"委派：{target_member.display_name}",
        model=target_agent.model_alias,
    )
    session.add(child_session)
    await session.flush()
    child_run = AgentRun(
        tenant_id=tenant_id,
        session_id=child_session.id,
        status="queued",
        input=task,
        limits=build_limits(target_agent, None),
    )
    session.add(child_run)
    await session.flush()
    delegation = AgentDelegation(
        tenant_id=tenant_id,
        parent_run_id=parent_run.id,
        parent_session_id=parent_session.id,
        parent_agent_id=parent_agent.id,
        child_agent_id=target_agent.id,
        child_session_id=child_session.id,
        child_run_id=child_run.id,
        task=task,
        status="queued",
    )
    session.add(delegation)
    await session.flush()
    return delegation


async def get_delegation(
    session: AsyncSession, tenant_id: uuid.UUID, delegation_id: uuid.UUID
) -> AgentDelegation:
    delegation = await session.scalar(
        select(AgentDelegation)
        .where(
            AgentDelegation.tenant_id == tenant_id,
            AgentDelegation.id == delegation_id,
        )
        .execution_options(populate_existing=True)
    )
    if delegation is None:
        raise ApiError(404, "delegation_not_found", "委派任务不存在")
    return delegation


async def finalize_delegations(session: AsyncSession, run: AgentRun) -> None:
    """Update delegations whose child run just finished, and notify the parent session."""
    delegations = (
        await session.scalars(
            select(AgentDelegation).where(
                AgentDelegation.tenant_id == run.tenant_id,
                AgentDelegation.child_run_id == run.id,
            )
        )
    ).all()
    if not delegations:
        return
    mapping = {
        "completed": "completed",
        "failed": "failed",
        "timeout": "failed",
        "cancelled": "cancelled",
    }
    for delegation in delegations:
        delegation.status = mapping.get(run.status, "failed")
        delegation.summary = (run.output or run.error or "")[:4000] or None
        delegation.result = {
            "output": run.output,
            "error": run.error,
            "steps": run.steps,
            "tool_calls": run.tool_calls_count,
        }
        delegation.error = run.error
        delegation.completed_at = datetime.now(UTC)
        session.add(
            AgentSessionMessage(
                tenant_id=run.tenant_id,
                session_id=delegation.parent_session_id,
                role="system",
                content=(
                    f"子 Agent 委派任务已完成（{delegation.status}）："
                    f"{delegation.summary or delegation.error or '无结果'}"
                ),
            )
        )


async def list_delegations_for_session(
    session: AsyncSession, tenant_id: uuid.UUID, session_id: uuid.UUID
) -> list[AgentDelegation]:
    return list(
        (
            await session.scalars(
                select(AgentDelegation)
                .where(
                    AgentDelegation.tenant_id == tenant_id,
                    AgentDelegation.parent_session_id == session_id,
                )
                .order_by(AgentDelegation.created_at)
            )
        ).all()
    )


async def child_session_count(
    session: AsyncSession, tenant_id: uuid.UUID, session_id: uuid.UUID
) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(AgentSession)
            .where(
                AgentSession.tenant_id == tenant_id,
                AgentSession.parent_session_id == session_id,
            )
        )
        or 0
    )


def delegation_result(delegation: AgentDelegation) -> dict[str, Any]:
    return {
        "delegation_id": str(delegation.id),
        "status": delegation.status,
        "child_session_id": str(delegation.child_session_id),
        "child_run_id": str(delegation.child_run_id) if delegation.child_run_id else None,
        "summary": delegation.summary,
        "result": delegation.result,
        "error": delegation.error,
    }


async def set_tenant_context(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


def agent_job_payload(delegation: AgentDelegation, tenant_id: uuid.UUID) -> dict[str, str]:
    return {
        "run_id": str(delegation.child_run_id),
        "session_id": str(delegation.child_session_id),
        "tenant_id": str(tenant_id),
    }


__all__ = [
    "agent_job_payload",
    "available_agents",
    "create_delegation",
    "delegation_result",
    "finalize_delegations",
    "get_delegation",
    "list_delegations_for_session",
    "resolve_target",
    "set_tenant_context",
]
