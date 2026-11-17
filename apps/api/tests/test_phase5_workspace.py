"""Shared agent workspace and Skill Runner test execution (MVP checkpoint enabler)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator

import pytest
from app.application.tools import ToolContext, execute_tool
from app.main import app
from app.models import AgentConfig, AgentSession, Member
from fastapi.testclient import TestClient
from orgweave_shared.settings import OrgWeaveSettings
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery"


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def _setup(client: TestClient) -> dict:
    suffix = uuid.uuid4().hex[:10]
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"workspace-{suffix}@example.com",
            "password": PASSWORD,
            "display_name": "Workspace Owner",
        },
    ).json()
    headers = {"Authorization": f"Bearer {registered['access_token']}"}
    tenant = client.post(
        "/api/v1/tenants", headers=headers, json={"name": f"Workspace-{suffix}"}
    ).json()
    tenant_headers = {**headers, "X-Tenant-ID": tenant["id"]}
    client.post(
        "/api/v1/members",
        headers=tenant_headers,
        json={
            "member_type": "ai",
            "display_name": "Developer-AI",
            "title": "开发工程师",
            "role_keys": ["admin"],
        },
    ).raise_for_status()
    agent = client.get("/api/v1/agents", headers=tenant_headers).json()[0]
    session = client.post(
        f"/api/v1/agents/{agent['id']}/sessions",
        headers=tenant_headers,
        json={"title": "代码交付"},
    ).json()
    return {
        "tenant_id": tenant["id"],
        "agent": agent,
        "session": session,
    }


async def _tool_async(setup: dict, tool: str, args: dict) -> dict:
    settings = OrgWeaveSettings()
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        async with factory() as session:
            await session.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"),
                {"t": setup["tenant_id"]},
            )
            agent = await session.get(AgentConfig, uuid.UUID(setup["agent"]["id"]))
            assert agent is not None
            member = await session.get(Member, agent.member_id)
            assert member is not None
            context = ToolContext(
                session=session,
                tenant_id=uuid.UUID(setup["tenant_id"]),
                agent_id=agent.id,
                session_id=uuid.UUID(setup["session"]["id"]),
                parent_agent=agent,
                session_factory=factory,
                redis=redis,
                settings=settings,
            )
            result = await execute_tool(tool, context, args)
            await session.commit()
            return result
    finally:
        await redis.aclose()
        await engine.dispose()


def test_workspace_write_read_list_and_run_tests(client: TestClient) -> None:
    setup = _setup(client)
    source = "def add(a, b):\n    return a + b\n"
    test_source = "from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n"

    written = asyncio.run(
        _tool_async(setup, "workspace_write_file", {"path": "calc.py", "content": source})
    )
    assert written["path"] == "calc.py"
    asyncio.run(
        _tool_async(setup, "workspace_write_file", {"path": "test_calc.py", "content": test_source})
    )

    listing = asyncio.run(_tool_async(setup, "workspace_list_files", {}))
    assert sorted(listing["files"]) == ["calc.py", "test_calc.py"]

    read = asyncio.run(_tool_async(setup, "workspace_read_file", {"path": "calc.py"}))
    assert "def add" in read["content"]

    passed = asyncio.run(_tool_async(setup, "run_tests", {"timeout_seconds": 30}))
    assert passed["exit_code"] == 0, passed
    assert passed["passed"] is True
    assert "passed" in passed["stdout"]

    failing = "from calc import add\n\ndef test_wrong():\n    assert add(2, 3) == 6\n"
    asyncio.run(
        _tool_async(
            setup,
            "workspace_write_file",
            {"path": "test_calc.py", "content": failing},
        )
    )
    failed = asyncio.run(_tool_async(setup, "run_tests", {"timeout_seconds": 30}))
    assert failed["exit_code"] != 0
    assert failed["passed"] is False
    assert "failed" in failed["stdout"]


def test_workspace_rejects_path_traversal(client: TestClient) -> None:
    setup = _setup(client)
    with pytest.raises(ValueError, match="invalid workspace path"):
        asyncio.run(
            _tool_async(
                setup,
                "workspace_write_file",
                {"path": "../../etc/passwd", "content": "x"},
            )
        )


def test_workspace_is_shared_across_child_sessions(client: TestClient) -> None:
    """A delegated child session reads the parent workspace root."""
    setup = _setup(client)
    session_id = setup["session"]["id"]

    # Create a child session directly in the database to model a delegation.
    async def create_child() -> str:
        settings = OrgWeaveSettings()
        engine = create_async_engine(settings.database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                await session.execute(
                    text("SELECT set_config('app.tenant_id', :t, true)"),
                    {"t": setup["tenant_id"]},
                )
                agent = await session.get(AgentConfig, uuid.UUID(setup["agent"]["id"]))
                assert agent is not None
                child = AgentSession(
                    tenant_id=uuid.UUID(setup["tenant_id"]),
                    agent_id=agent.id,
                    member_id=agent.member_id,
                    parent_session_id=uuid.UUID(session_id),
                    title="child",
                )
                session.add(child)
                await session.commit()
                return str(child.id)
        finally:
            await engine.dispose()

    child_id = asyncio.run(create_child())
    asyncio.run(
        _tool_async(
            setup,
            "workspace_write_file",
            {"path": "shared.py", "content": "VALUE = 42\n"},
        )
    )

    async def read_from_child() -> dict:
        settings = OrgWeaveSettings()
        engine = create_async_engine(settings.database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            async with factory() as session:
                await session.execute(
                    text("SELECT set_config('app.tenant_id', :t, true)"),
                    {"t": setup["tenant_id"]},
                )
                agent = await session.get(AgentConfig, uuid.UUID(setup["agent"]["id"]))
                assert agent is not None
                context = ToolContext(
                    session=session,
                    tenant_id=uuid.UUID(setup["tenant_id"]),
                    agent_id=agent.id,
                    session_id=uuid.UUID(child_id),
                    parent_agent=agent,
                    session_factory=factory,
                    redis=redis,
                    settings=settings,
                )
                return await execute_tool("workspace_read_file", context, {"path": "shared.py"})
        finally:
            await redis.aclose()
            await engine.dispose()

    shared = asyncio.run(read_from_child())
    assert shared["content"] == "VALUE = 42\n"
