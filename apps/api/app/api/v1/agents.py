"""Agent configuration, sessions, runs, tools and memory APIs."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from orgweave_agent_sdk import AgentJob
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    TenantContext,
    get_session,
    get_tenant_context,
    require_permission,
    set_tenant_context,
)
from app.application import agent_service
from app.application.agent_runtime import CANCEL_KEY
from app.application.audit import record_audit
from app.core.errors import ApiError
from app.models import AgentDelegation, AgentMemory, AgentSession, Member
from app.schemas.agent import (
    AgentCreate,
    AgentOut,
    AgentUpdate,
    DelegationOut,
    MemoryCreate,
    MemoryOut,
    RunCreate,
    RunOut,
    SessionCreate,
    SessionMessageOut,
    SessionOut,
    ToolCallOut,
)

router = APIRouter(tags=["agents"])


@router.get("/agents", response_model=list[AgentOut], summary="List AI agent configurations")
async def list_agents(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[AgentOut]:
    rows = (
        await session.execute(
            select(agent_service.AgentConfig, Member)
            .join(
                Member,
                (Member.id == agent_service.AgentConfig.member_id)
                & (Member.tenant_id == agent_service.AgentConfig.tenant_id),
            )
            .where(agent_service.AgentConfig.tenant_id == context.tenant_id)
            .order_by(Member.display_name)
        )
    ).all()
    await session.commit()
    return [agent_service.serialize_agent(agent, member) for agent, member in rows]


@router.post(
    "/agents",
    response_model=AgentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an agent configuration for an AI member",
)
async def create_agent(
    body: AgentCreate,
    context: Annotated[TenantContext, Depends(require_permission("member.manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AgentOut:
    agent = await agent_service.create_agent(session, context.tenant_id, body)
    member = await session.get(Member, agent.member_id)
    record_audit(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_id=context.user_id,
        action="agent.created",
        resource_type="agent",
        resource_id=agent.id,
        metadata={"member_id": str(agent.member_id)},
    )
    await session.commit()
    return agent_service.serialize_agent(agent, member)  # type: ignore[arg-type]


@router.get("/agents/{agent_id}", response_model=AgentOut, summary="Get agent configuration")
async def get_agent(
    agent_id: uuid.UUID,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AgentOut:
    agent = await agent_service.get_agent(session, context.tenant_id, agent_id)
    member = await session.get(Member, agent.member_id)
    if member is None:
        raise ApiError(404, "agent_member_missing", "AI 成员不存在")
    await session.commit()
    return agent_service.serialize_agent(agent, member)


@router.patch("/agents/{agent_id}", response_model=AgentOut, summary="Update agent configuration")
async def update_agent(
    agent_id: uuid.UUID,
    body: AgentUpdate,
    context: Annotated[TenantContext, Depends(require_permission("member.manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AgentOut:
    agent = await agent_service.get_agent(session, context.tenant_id, agent_id)
    await agent_service.update_agent(session, agent, body)
    member = await session.get(Member, agent.member_id)
    record_audit(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_id=context.user_id,
        action="agent.updated",
        resource_type="agent",
        resource_id=agent.id,
        metadata={"fields": sorted(body.model_fields_set)},
    )
    await session.commit()
    await set_tenant_context(session, context.tenant_id)
    await session.refresh(agent)
    if member is not None:
        await session.refresh(member)
    return agent_service.serialize_agent(agent, member)  # type: ignore[arg-type]


@router.get(
    "/agents/{agent_id}/sessions",
    response_model=list[SessionOut],
    summary="List sessions for an agent",
)
async def list_sessions(
    agent_id: uuid.UUID,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[SessionOut]:
    await agent_service.get_agent(session, context.tenant_id, agent_id)
    rows = (
        await session.scalars(
            select(AgentSession)
            .where(
                AgentSession.tenant_id == context.tenant_id,
                AgentSession.agent_id == agent_id,
            )
            .order_by(AgentSession.created_at.desc())
            .limit(100)
        )
    ).all()
    result = [await agent_service.session_out(session, row) for row in rows]
    await session.commit()
    return result


@router.post(
    "/agents/{agent_id}/sessions",
    response_model=SessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an independent agent session",
)
async def create_session(
    agent_id: uuid.UUID,
    body: SessionCreate,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SessionOut:
    agent = await agent_service.get_agent(session, context.tenant_id, agent_id)
    agent_session = await agent_service.create_session(
        session, context.tenant_id, agent, title=body.title
    )
    record_audit(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_id=context.user_id,
        action="agent.session_created",
        resource_type="session",
        resource_id=agent_session.id,
        metadata={"agent_id": str(agent.id)},
    )
    await session.commit()
    return await agent_service.session_out(session, agent_session)


@router.get("/sessions/{session_id}", response_model=SessionOut, summary="Get a session")
async def get_session_detail(
    session_id: uuid.UUID,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SessionOut:
    agent_session = await agent_service.get_session(session, context.tenant_id, session_id)
    result = await agent_service.session_out(session, agent_session)
    await session.commit()
    return result


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[SessionMessageOut],
    summary="Session conversation and tool messages",
)
async def get_session_messages(
    session_id: uuid.UUID,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[SessionMessageOut]:
    await agent_service.get_session(session, context.tenant_id, session_id)
    rows = await agent_service.list_session_messages(session, context.tenant_id, session_id)
    await session.commit()
    return [
        SessionMessageOut(
            id=row.id,
            role=row.role,
            content=row.content,
            tool_calls=row.tool_calls,
            tool_call_id=row.tool_call_id,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post(
    "/sessions/{session_id}/runs",
    response_model=RunOut,
    status_code=status.HTTP_201_CREATED,
    summary="Queue a run in a session",
)
async def create_run(
    session_id: uuid.UUID,
    body: RunCreate,
    request: Request,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RunOut:
    agent_session = await agent_service.get_session(session, context.tenant_id, session_id)
    if agent_session.status == "killed":
        raise ApiError(409, "session_killed", "会话已被终止")
    agent = await agent_service.get_agent(session, context.tenant_id, agent_session.agent_id)
    limits = body.limits.model_dump(exclude_none=True) if body.limits else None
    run = await agent_service.create_run(
        session, agent_session, agent, input_text=body.input, limits=limits
    )
    record_audit(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_id=context.user_id,
        action="agent.run_queued",
        resource_type="run",
        resource_id=run.id,
        metadata={"session_id": str(session_id)},
    )
    await session.commit()

    job = AgentJob(
        type="agent.run",
        payload={
            "run_id": str(run.id),
            "session_id": str(session_id),
            "tenant_id": str(context.tenant_id),
        },
    )
    try:
        await request.app.state.redis.lpush(
            request.app.state.settings.agent_queue, job.model_dump_json()
        )
    except Exception as exc:
        run.status = "failed"
        run.error = "queue_unavailable"
        await session.commit()
        raise ApiError(503, "queue_unavailable", "任务队列不可用") from exc
    return agent_service.run_out(run)


@router.get("/runs/{run_id}", response_model=RunOut, summary="Get a run")
async def get_run(
    run_id: uuid.UUID,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RunOut:
    run = await agent_service.get_run(session, context.tenant_id, run_id)
    await session.commit()
    return agent_service.run_out(run)


@router.get(
    "/runs/{run_id}/tools",
    response_model=list[ToolCallOut],
    summary="Tool calls recorded for a run",
)
async def get_run_tools(
    run_id: uuid.UUID,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ToolCallOut]:
    await agent_service.get_run(session, context.tenant_id, run_id)
    rows = await agent_service.list_tool_calls(session, context.tenant_id, run_id)
    await session.commit()
    return [
        ToolCallOut(
            id=row.id,
            run_id=row.run_id,
            tool_name=row.tool_name,
            arguments=row.arguments,
            result=row.result,
            status=row.status,
            error=row.error,
            created_at=row.created_at,
            completed_at=row.completed_at,
        )
        for row in rows
    ]


@router.post(
    "/runs/{run_id}/cancel",
    response_model=RunOut,
    summary="Cancel a queued or running agent run",
)
async def cancel_run(
    run_id: uuid.UUID,
    request: Request,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RunOut:
    run = await agent_service.get_run(session, context.tenant_id, run_id)
    if run.status not in {"queued", "running"}:
        raise ApiError(409, "run_not_cancellable", "该执行已结束")
    await request.app.state.redis.set(CANCEL_KEY.format(run_id=run.id), "1", ex=3600)
    await agent_service.cancel_run(session, context.tenant_id, run)
    record_audit(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_id=context.user_id,
        action="agent.run_cancel_requested",
        resource_type="run",
        resource_id=run.id,
    )
    await session.commit()
    return agent_service.run_out(run)


def _delegation_out(row: AgentDelegation) -> DelegationOut:
    return DelegationOut(
        id=row.id,
        parent_run_id=row.parent_run_id,
        parent_session_id=row.parent_session_id,
        parent_agent_id=row.parent_agent_id,
        child_agent_id=row.child_agent_id,
        child_session_id=row.child_session_id,
        child_run_id=row.child_run_id,
        task=row.task,
        status=row.status,
        summary=row.summary,
        result=row.result,
        error=row.error,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


@router.get(
    "/sessions/{session_id}/delegations",
    response_model=list[DelegationOut],
    summary="Delegations created by a session",
)
async def list_session_delegations(
    session_id: uuid.UUID,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[DelegationOut]:
    await agent_service.get_session(session, context.tenant_id, session_id)
    rows = (
        await session.scalars(
            select(AgentDelegation)
            .where(
                AgentDelegation.tenant_id == context.tenant_id,
                AgentDelegation.parent_session_id == session_id,
            )
            .order_by(AgentDelegation.created_at)
        )
    ).all()
    await session.commit()
    return [_delegation_out(row) for row in rows]


@router.get(
    "/sessions/{session_id}/children",
    response_model=list[SessionOut],
    summary="Child sessions created by delegation",
)
async def list_child_sessions(
    session_id: uuid.UUID,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[SessionOut]:
    await agent_service.get_session(session, context.tenant_id, session_id)
    rows = (
        await session.scalars(
            select(AgentSession)
            .where(
                AgentSession.tenant_id == context.tenant_id,
                AgentSession.parent_session_id == session_id,
            )
            .order_by(AgentSession.created_at)
        )
    ).all()
    result = [await agent_service.session_out(session, row) for row in rows]
    await session.commit()
    return result


@router.get(
    "/delegations/{delegation_id}",
    response_model=DelegationOut,
    summary="Get a delegation",
)
async def get_delegation_detail(
    delegation_id: uuid.UUID,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DelegationOut:
    row = await session.scalar(
        select(AgentDelegation).where(
            AgentDelegation.tenant_id == context.tenant_id,
            AgentDelegation.id == delegation_id,
        )
    )
    if row is None:
        raise ApiError(404, "delegation_not_found", "委派任务不存在")
    await session.commit()
    return _delegation_out(row)


@router.get(
    "/agents/{agent_id}/memories",
    response_model=list[MemoryOut],
    summary="List an agent's private memories",
)
async def list_memories(
    agent_id: uuid.UUID,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[MemoryOut]:
    await agent_service.get_agent(session, context.tenant_id, agent_id)
    rows = (
        await session.scalars(
            select(AgentMemory)
            .where(
                AgentMemory.tenant_id == context.tenant_id,
                AgentMemory.agent_id == agent_id,
            )
            .order_by(AgentMemory.created_at.desc())
            .limit(200)
        )
    ).all()
    await session.commit()
    return [
        MemoryOut(
            id=row.id,
            agent_id=row.agent_id,
            memory_type=row.memory_type,
            content=row.content,
            importance=row.importance,
            source_session_id=row.source_session_id,
            metadata=row.metadata_,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post(
    "/agents/{agent_id}/memories",
    response_model=MemoryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add an agent-private memory",
)
async def add_memory(
    agent_id: uuid.UUID,
    body: MemoryCreate,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MemoryOut:
    await agent_service.get_agent(session, context.tenant_id, agent_id)
    memory = AgentMemory(
        tenant_id=context.tenant_id,
        agent_id=agent_id,
        memory_type=body.memory_type,
        content=body.content,
        importance=body.importance,
        metadata_={"source": "manual"},
    )
    session.add(memory)
    record_audit(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_id=context.user_id,
        action="agent.memory_added",
        resource_type="memory",
        resource_id=memory.id,
        metadata={"agent_id": str(agent_id)},
    )
    await session.commit()
    return MemoryOut(
        id=memory.id,
        agent_id=memory.agent_id,
        memory_type=memory.memory_type,
        content=memory.content,
        importance=memory.importance,
        source_session_id=memory.source_session_id,
        metadata=memory.metadata_,
        created_at=memory.created_at,
    )
