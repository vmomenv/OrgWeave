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

from app.models import AgentMemory, Member

ToolHandler = Callable[["ToolContext", dict[str, Any]], Awaitable[dict[str, Any]]]

DEFAULT_TOOLS = ["get_current_time", "list_team_members", "remember", "search_memory"]


@dataclass(frozen=True)
class ToolContext:
    session: AsyncSession
    tenant_id: uuid.UUID
    agent_id: uuid.UUID
    session_id: uuid.UUID


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


_HANDLERS: dict[str, ToolHandler] = {
    "get_current_time": _get_current_time,
    "list_team_members": _list_team_members,
    "remember": _remember,
    "search_memory": _search_memory,
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
