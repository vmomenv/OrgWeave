"""Server-side tool registry for the Phase 3 Agent Runtime."""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentConfig, AgentMemory, AgentRun, AgentSession, Member

ToolHandler = Callable[["ToolContext", dict[str, Any]], Awaitable[dict[str, Any]]]

DEFAULT_TOOLS = [
    "get_current_time",
    "list_team_members",
    "remember",
    "search_memory",
    "list_available_agents",
    "delegate_task",
    "get_task_status",
    "get_task_result",
    "cancel_delegated_task",
    "send_message_to_agent",
    "request_agent_review",
]


@dataclass(frozen=True)
class ToolContext:
    session: AsyncSession
    tenant_id: uuid.UUID
    agent_id: uuid.UUID
    session_id: uuid.UUID
    parent_run_id: uuid.UUID | None = None
    parent_agent: AgentConfig | None = None
    session_factory: Any | None = None
    redis: Any | None = None
    settings: Any | None = None


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "get_current_time": {
        "description": "Return the current UTC time in ISO-8601 format.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "list_team_members": {
        "description": "List members of the current organization with type, title and status.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20}
            },
            "additionalProperties": False,
        },
    },
    "remember": {
        "description": "Store a durable memory for this agent.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "minLength": 1, "maxLength": 4000},
                "memory_type": {
                    "type": "string",
                    "enum": ["semantic", "episodic", "procedural", "task"],
                    "default": "episodic",
                },
                "importance": {"type": "integer", "minimum": 1, "maximum": 5, "default": 3},
            },
            "required": ["content"],
            "additionalProperties": False,
        },
    },
    "list_available_agents": {
        "description": "List AI employees that this agent is authorized to delegate to.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "delegate_task": {
        "description": (
            "Delegate a task to another AI employee. By default waits for the child "
            "session to finish and returns its result."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
                "agent_name": {"type": "string"},
                "task": {"type": "string", "minLength": 1, "maxLength": 8000},
                "wait": {"type": "boolean", "default": True},
            },
            "required": ["task"],
            "additionalProperties": False,
        },
    },
    "get_task_status": {
        "description": "Get the status of a delegated task.",
        "parameters": {
            "type": "object",
            "properties": {"delegation_id": {"type": "string"}},
            "required": ["delegation_id"],
            "additionalProperties": False,
        },
    },
    "get_task_result": {
        "description": "Get the stored result of a delegated task.",
        "parameters": {
            "type": "object",
            "properties": {"delegation_id": {"type": "string"}},
            "required": ["delegation_id"],
            "additionalProperties": False,
        },
    },
    "cancel_delegated_task": {
        "description": "Cancel a delegated task if it is still queued or running.",
        "parameters": {
            "type": "object",
            "properties": {"delegation_id": {"type": "string"}},
            "required": ["delegation_id"],
            "additionalProperties": False,
        },
    },
    "send_message_to_agent": {
        "description": "Send work to another AI employee and optionally wait for the result.",
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
                "agent_name": {"type": "string"},
                "message": {"type": "string", "minLength": 1, "maxLength": 8000},
                "wait": {"type": "boolean", "default": True},
            },
            "required": ["message"],
            "additionalProperties": False,
        },
    },
    "request_agent_review": {
        "description": "Ask another AI employee to review a deliverable or plan.",
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
                "agent_name": {"type": "string"},
                "content": {"type": "string", "minLength": 1, "maxLength": 8000},
                "wait": {"type": "boolean", "default": True},
            },
            "required": ["content"],
            "additionalProperties": False,
        },
    },
    "search_memory": {
        "description": "Search this agent's private memories by text.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 200},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 10},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}


def tool_definitions(allowed: list[str]) -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = []
    for name in allowed:
        schema = TOOL_SCHEMAS.get(name)
        if schema is None:
            continue
        definitions.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": schema["description"],
                    "parameters": schema["parameters"],
                },
            }
        )
    return definitions


async def _get_current_time(_: ToolContext, __: dict[str, Any]) -> dict[str, Any]:
    return {"utc": datetime.now(UTC).isoformat()}


async def _list_team_members(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    limit = min(max(int(arguments.get("limit", 20)), 1), 50)
    members = (
        await context.session.scalars(
            select(Member)
            .where(Member.tenant_id == context.tenant_id)
            .order_by(Member.created_at)
            .limit(limit)
        )
    ).all()
    return {
        "members": [
            {
                "id": str(member.id),
                "name": member.display_name,
                "type": member.member_type,
                "title": member.title,
                "status": member.status,
                "ai_enabled": member.ai_enabled,
            }
            for member in members
        ]
    }


async def _remember(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    content = str(arguments.get("content", "")).strip()
    if not content:
        raise ValueError("content is required")
    memory_type = str(arguments.get("memory_type", "episodic"))
    if memory_type not in {"semantic", "episodic", "procedural", "task"}:
        memory_type = "episodic"
    importance = min(max(int(arguments.get("importance", 3)), 1), 5)
    memory = AgentMemory(
        tenant_id=context.tenant_id,
        agent_id=context.agent_id,
        memory_type=memory_type,
        content=content[:4000],
        importance=importance,
        source_session_id=context.session_id,
        metadata_={"source": "tool"},
    )
    context.session.add(memory)
    await context.session.flush()
    return {"memory_id": str(memory.id), "stored": True}


async def _search_memory(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    query = str(arguments.get("query", "")).strip()
    if not query:
        raise ValueError("query is required")
    limit = min(max(int(arguments.get("limit", 10)), 1), 20)
    pattern = f"%{query[:200]}%"
    memories = (
        await context.session.scalars(
            select(AgentMemory)
            .where(
                AgentMemory.tenant_id == context.tenant_id,
                AgentMemory.agent_id == context.agent_id,
                or_(
                    AgentMemory.content.ilike(pattern),
                    AgentMemory.memory_type.ilike(pattern),
                ),
            )
            .order_by(AgentMemory.importance.desc(), AgentMemory.created_at.desc())
            .limit(limit)
        )
    ).all()
    return {
        "memories": [
            {
                "id": str(memory.id),
                "type": memory.memory_type,
                "content": memory.content,
                "importance": memory.importance,
                "created_at": memory.created_at.isoformat(),
            }
            for memory in memories
        ]
    }


async def _list_available_agents(context: ToolContext, _: dict[str, Any]) -> dict[str, Any]:
    from app.application.delegation import available_agents

    if context.parent_agent is None:
        raise ValueError("agent context unavailable")
    agents = await available_agents(context.session, context.tenant_id, context.parent_agent)
    return {"agents": agents}


async def _delegate(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    from app.application.delegation import (
        create_delegation,
        delegation_result,
        get_delegation,
        resolve_target,
        set_tenant_context,
    )

    if context.parent_agent is None or context.parent_run_id is None:
        raise ValueError("delegation context unavailable")
    task = str(arguments.get("task", "")).strip()
    if not task:
        raise ValueError("task is required")
    target_agent, target_member = await resolve_target(
        context.session,
        context.tenant_id,
        context.parent_agent,
        agent_id=str(arguments["agent_id"]) if arguments.get("agent_id") else None,
        agent_name=str(arguments["agent_name"]) if arguments.get("agent_name") else None,
    )
    parent_run = await context.session.get(AgentRun, context.parent_run_id)
    parent_session = await context.session.get(AgentSession, context.session_id)
    if parent_run is None or parent_session is None:
        raise ValueError("parent run/session missing")
    delegation = await create_delegation(
        context.session,
        tenant_id=context.tenant_id,
        parent_run=parent_run,
        parent_session=parent_session,
        parent_agent=context.parent_agent,
        target_agent=target_agent,
        target_member=target_member,
        task=task,
    )
    delegation_id = delegation.id
    child_run_id = delegation.child_run_id
    # Persist the child session/run before another session executes it.
    await context.session.commit()
    await set_tenant_context(context.session, context.tenant_id)

    wait = bool(arguments.get("wait", True))
    if not wait:
        if context.redis is None:
            raise ValueError("queue unavailable")
        from orgweave_agent_sdk import AgentJob

        job = AgentJob(
            type="agent.run",
            payload={
                "run_id": str(child_run_id),
                "session_id": str(delegation.child_session_id),
                "tenant_id": str(context.tenant_id),
            },
        )
        await context.redis.lpush("orgweave:agent:jobs", job.model_dump_json())
        delegation = await get_delegation(context.session, context.tenant_id, delegation_id)
        return delegation_result(delegation)

    if context.session_factory is None or context.redis is None or context.settings is None:
        raise ValueError("synchronous delegation unavailable in this runtime")
    from app.application.agent_runtime import execute_run

    async with context.session_factory() as child_session:
        await set_tenant_context(child_session, context.tenant_id)
        await execute_run(
            child_session,
            context.redis,
            context.settings,
            child_run_id,
            session_factory=context.session_factory,
        )
    await set_tenant_context(context.session, context.tenant_id)
    delegation = await get_delegation(context.session, context.tenant_id, delegation_id)
    return delegation_result(delegation)


async def _get_task_status(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    from app.application.delegation import delegation_result, get_delegation

    delegation = await get_delegation(
        context.session, context.tenant_id, uuid.UUID(str(arguments["delegation_id"]))
    )
    payload = delegation_result(delegation)
    return {"delegation_id": payload["delegation_id"], "status": payload["status"]}


async def _get_task_result(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    from app.application.delegation import delegation_result, get_delegation

    delegation = await get_delegation(
        context.session, context.tenant_id, uuid.UUID(str(arguments["delegation_id"]))
    )
    return delegation_result(delegation)


async def _cancel_delegated_task(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    from app.application.delegation import get_delegation, set_tenant_context

    delegation = await get_delegation(
        context.session, context.tenant_id, uuid.UUID(str(arguments["delegation_id"]))
    )
    if context.redis is None:
        raise ValueError("queue unavailable")
    if delegation.child_run_id is not None:
        await context.redis.set(f"orgweave:agent:cancel:{delegation.child_run_id}", "1", ex=3600)
    if delegation.status in {"queued", "running"}:
        delegation.status = "cancelled"
        delegation.error = "cancelled_by_parent"
        delegation.completed_at = datetime.now(UTC)
        await context.session.commit()
        await set_tenant_context(context.session, context.tenant_id)
    return {"delegation_id": str(delegation.id), "status": delegation.status}


async def _send_message_to_agent(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    return await _delegate(
        context,
        {
            "agent_id": arguments.get("agent_id"),
            "agent_name": arguments.get("agent_name"),
            "task": str(arguments.get("message", "")),
            "wait": arguments.get("wait", True),
        },
    )


async def _request_agent_review(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    return await _delegate(
        context,
        {
            "agent_id": arguments.get("agent_id"),
            "agent_name": arguments.get("agent_name"),
            "task": f"请审查以下内容并给出问题、建议与结论：\n{arguments.get('content', '')}",
            "wait": arguments.get("wait", True),
        },
    )


_HANDLERS: dict[str, ToolHandler] = {
    "get_current_time": _get_current_time,
    "list_team_members": _list_team_members,
    "remember": _remember,
    "search_memory": _search_memory,
    "list_available_agents": _list_available_agents,
    "delegate_task": _delegate,
    "get_task_status": _get_task_status,
    "get_task_result": _get_task_result,
    "cancel_delegated_task": _cancel_delegated_task,
    "send_message_to_agent": _send_message_to_agent,
    "request_agent_review": _request_agent_review,
}


async def execute_tool(
    name: str, context: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    handler = _HANDLERS.get(name)
    if handler is None:
        raise ValueError(f"unknown tool: {name}")
    return await handler(context, arguments)


def parse_arguments(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("tool arguments are not valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("tool arguments must be a JSON object")
    return value
