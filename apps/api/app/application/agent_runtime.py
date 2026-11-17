"""Agent Runtime execution engine (Phase 3).

One run executes inside a worker process with a tenant-scoped database session.
Hard limits are enforced by deterministic server-side code; the model cannot
extend them.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.tools import (
    TOOL_SCHEMAS,
    ToolContext,
    execute_tool,
    parse_arguments,
    tool_definitions,
)
from app.core.config import OrgWeaveSettings
from app.infrastructure.model_gateway import ModelGatewayError, chat_completion
from app.models import (
    AgentConfig,
    AgentMemory,
    AgentRun,
    AgentSession,
    AgentSessionMessage,
    AgentToolCall,
    Member,
)

logger = logging.getLogger("orgweave.agent_runtime")

HISTORY_LIMIT = 20
CANCEL_KEY = "orgweave:agent:cancel:{run_id}"


def _default_limits(agent: AgentConfig) -> dict[str, Any]:
    return {
        "max_steps": agent.max_steps,
        "max_duration_seconds": agent.max_duration_seconds,
        "token_budget": agent.token_budget,
        "cost_budget_usd": float(agent.cost_budget_usd),
        "max_tool_calls": agent.max_tool_calls,
        "max_consecutive_failures": agent.max_consecutive_failures,
    }


def build_limits(agent: AgentConfig, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    limits = _default_limits(agent)
    if overrides:
        for key in limits:
            if key in overrides and overrides[key] is not None:
                limits[key] = overrides[key]
    limits["max_steps"] = min(max(int(limits["max_steps"]), 1), 100)
    limits["max_tool_calls"] = min(max(int(limits["max_tool_calls"]), 0), 200)
    return limits


def _system_prompt(agent: AgentConfig, member: Member) -> str:
    base = agent.system_prompt.strip()
    if base:
        return base
    return (
        f"你是 {member.display_name}，岗位：{member.title or '组织成员'}。"
        "你是 OrgWeave 企业中的 AI 员工。请基于事实完成任务，必要时使用工具。"
        "你不能修改或绕过任务限制，也不能访问其他租户的数据。"
    )


async def _history(
    session: AsyncSession, tenant_id: uuid.UUID, session_id: uuid.UUID
) -> list[AgentSessionMessage]:
    rows = (
        await session.scalars(
            select(AgentSessionMessage)
            .where(
                AgentSessionMessage.tenant_id == tenant_id,
                AgentSessionMessage.session_id == session_id,
            )
            .order_by(AgentSessionMessage.created_at.desc())
            .limit(HISTORY_LIMIT)
        )
    ).all()
    return list(reversed(rows))


def _to_model_message(row: AgentSessionMessage) -> dict[str, Any]:
    if row.role == "tool":
        return {
            "role": "tool",
            "content": row.content,
            "tool_call_id": row.tool_call_id,
        }
    if row.role == "assistant" and row.tool_calls:
        return {
            "role": "assistant",
            "content": row.content or None,
            "tool_calls": row.tool_calls,
        }
    return {"role": row.role, "content": row.content}


async def _publish(redis: Redis, tenant_id: uuid.UUID, payload: dict[str, Any]) -> None:
    try:
        await redis.publish(
            f"orgweave:events:tenant:{tenant_id}", json.dumps(payload, ensure_ascii=False)
        )
    except Exception:
        logger.exception("failed to publish agent event")


async def _fail_run(
    session: AsyncSession,
    run: AgentRun,
    agent_session: AgentSession,
    message: str,
) -> None:
    now = datetime.now(UTC)
    run.status = "failed"
    run.error = message[:2000]
    run.completed_at = now
    agent_session.status = "failed"
    agent_session.completed_at = now


async def execute_run(
    session: AsyncSession,
    redis: Redis,
    settings: OrgWeaveSettings,
    run_id: uuid.UUID,
    *,
    session_factory: Any | None = None,
) -> None:
    """Execute one queued run. Caller must set app.tenant_id first."""
    run = await session.get(AgentRun, run_id)
    if run is None:
        return
    if run.status != "queued":
        return
    agent_session = await session.get(AgentSession, run.session_id)
    if agent_session is None:
        return
    agent = await session.get(AgentConfig, agent_session.agent_id)
    member = await session.get(Member, agent_session.member_id)
    if agent is None or member is None:
        await _fail_run(session, run, agent_session, "agent_or_member_missing")
        await session.commit()
        return

    if agent_session.control_mode == "takeover" or agent_session.status == "killed":
        run.status = "cancelled"
        run.error = "session_not_autonomous"
        run.completed_at = datetime.now(UTC)
        await session.commit()
        return

    limits = build_limits(agent, run.limits)
    allowed_tools = [name for name in agent.allowed_tools if name in TOOL_SCHEMAS]
    tools = tool_definitions(allowed_tools)

    started = datetime.now(UTC)
    run.status = "running"
    run.started_at = started
    agent_session.status = "active"
    agent_session.started_at = agent_session.started_at or started
    agent_session.model = agent.model_alias
    await session.flush()

    history = await _history(session, run.tenant_id, run.session_id)
    messages: list[dict[str, Any]] = [{"role": "system", "content": _system_prompt(agent, member)}]
    for row in history:
        messages.append(_to_model_message(row))

    user_message = AgentSessionMessage(
        tenant_id=run.tenant_id,
        session_id=run.session_id,
        role="user",
        content=run.input,
    )
    session.add(user_message)
    messages.append({"role": "user", "content": run.input})

    tool_context = ToolContext(
        session=session,
        tenant_id=run.tenant_id,
        agent_id=agent.id,
        session_id=run.session_id,
        parent_run_id=run.id,
        parent_agent=agent,
        session_factory=session_factory,
        redis=redis,
        settings=settings,
    )
    consecutive_failures = 0
    assistant_output = ""

    try:
        for step in range(1, int(limits["max_steps"]) + 1):
            if await redis.get(CANCEL_KEY.format(run_id=run.id)):
                run.status = "cancelled"
                run.error = "cancelled_by_user"
                run.completed_at = datetime.now(UTC)
                agent_session.status = "paused"
                break

            elapsed = (datetime.now(UTC) - started).total_seconds()
            if elapsed > float(limits["max_duration_seconds"]):
                await _fail_run(session, run, agent_session, "max_duration_exceeded")
                break

            remaining = max(1, int(float(limits["max_duration_seconds"]) - elapsed))
            try:
                response = await chat_completion(
                    settings,
                    model=agent.model_alias,
                    messages=messages,
                    tools=tools,
                    temperature=float(agent.temperature),
                    max_tokens=agent.max_output_tokens,
                    timeout_seconds=min(240, remaining),
                )
            except ModelGatewayError as exc:
                await _fail_run(session, run, agent_session, str(exc))
                break

            usage = int(response["total_tokens"])
            run.token_usage += usage
            agent_session.token_usage += usage
            if run.token_usage > int(limits["token_budget"]):
                await _fail_run(session, run, agent_session, "token_budget_exceeded")
                break

            assistant = response["message"]
            tool_calls = assistant.get("tool_calls") or []
            content = assistant.get("content") or ""
            run.steps = step
            session.add(
                AgentSessionMessage(
                    tenant_id=run.tenant_id,
                    session_id=run.session_id,
                    role="assistant",
                    content=content,
                    tool_calls=tool_calls or None,
                )
            )
            messages.append(
                {"role": "assistant", "content": content or None, "tool_calls": tool_calls or None}
            )
            if content:
                assistant_output = content

            if not tool_calls:
                run.status = "completed"
                run.output = assistant_output
                run.completed_at = datetime.now(UTC)
                agent_session.status = "completed"
                agent_session.completed_at = datetime.now(UTC)
                agent_session.context_summary = assistant_output[:2000]
                break

            for raw_call in tool_calls:
                if run.tool_calls_count >= int(limits["max_tool_calls"]):
                    await _fail_run(session, run, agent_session, "max_tool_calls_exceeded")
                    break
                function = raw_call.get("function") or {}
                tool_name = str(function.get("name") or "")
                call_id = str(raw_call.get("id") or uuid.uuid4().hex)
                try:
                    arguments = parse_arguments(function.get("arguments"))
                except ValueError as exc:
                    arguments = {}
                    tool_error: str | None = str(exc)
                else:
                    tool_error = None

                tool_call = AgentToolCall(
                    tenant_id=run.tenant_id,
                    run_id=run.id,
                    session_id=run.session_id,
                    tool_call_id=call_id,
                    tool_name=tool_name,
                    arguments=arguments,
                    status="requested",
                    started_at=datetime.now(UTC),
                )
                session.add(tool_call)
                run.tool_calls_count += 1

                if tool_name not in allowed_tools:
                    tool_call.status = "denied"
                    tool_call.error = "tool_not_allowed"
                    result_payload = {"error": "tool_not_allowed"}
                    tool_error = "tool_not_allowed"
                elif tool_error is not None:
                    tool_call.status = "failed"
                    tool_call.error = tool_error
                    result_payload = {"error": tool_error}
                else:
                    try:
                        result_payload = await execute_tool(tool_name, tool_context, arguments)
                        tool_call.status = "completed"
                        tool_call.result = result_payload
                    except Exception as exc:
                        tool_error = exc.__class__.__name__
                        tool_call.status = "failed"
                        tool_call.error = str(exc)[:500]
                        result_payload = {"error": str(exc)[:500]}
                tool_call.completed_at = datetime.now(UTC)

                if tool_call.status == "completed":
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1

                result_content = json.dumps(result_payload, ensure_ascii=False, default=str)
                session.add(
                    AgentSessionMessage(
                        tenant_id=run.tenant_id,
                        session_id=run.session_id,
                        role="tool",
                        content=result_content,
                        tool_call_id=call_id,
                    )
                )
                messages.append(
                    {"role": "tool", "content": result_content, "tool_call_id": call_id}
                )

                if consecutive_failures >= int(limits["max_consecutive_failures"]):
                    await _fail_run(session, run, agent_session, "max_consecutive_tool_failures")
                    break
            if run.status != "running":
                break
        else:
            await _fail_run(session, run, agent_session, "max_steps_exceeded")

        from app.application.delegation import finalize_delegations

        await finalize_delegations(session, run)

        if run.status == "completed" and agent.memory_enabled and assistant_output:
            session.add(
                AgentMemory(
                    tenant_id=run.tenant_id,
                    agent_id=agent.id,
                    memory_type="episodic",
                    content=f"会话「{agent_session.title}」结果：{assistant_output[:2000]}",
                    importance=3,
                    source_session_id=agent_session.id,
                    metadata_={"run_id": str(run.id)},
                )
            )

        await session.commit()
    except Exception as exc:
        logger.exception("agent run crashed")
        await session.rollback()
        run = await session.get(AgentRun, run_id)
        agent_session = await session.get(AgentSession, run.session_id) if run is not None else None
        if run is not None and agent_session is not None:
            await _fail_run(session, run, agent_session, f"runtime_error: {exc.__class__.__name__}")
            await session.commit()

    await _publish(
        redis,
        run.tenant_id,
        {
            "type": "agent.run.updated",
            "tenant_id": str(run.tenant_id),
            "session_id": str(run.session_id),
            "run_id": str(run.id),
            "status": run.status,
            "steps": run.steps,
            "tool_calls": run.tool_calls_count,
            "token_usage": run.token_usage,
        },
    )
