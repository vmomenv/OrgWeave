"""Phase 3 Agent Runtime tests with a deterministic OpenAI-compatible model stub."""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from collections import deque
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import pytest
from app.application.agent_runtime import CANCEL_KEY, execute_run
from app.main import app
from fastapi.testclient import TestClient
from orgweave_shared.settings import OrgWeaveSettings
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery"


class StubModelHandler(BaseHTTPRequestHandler):
    responses: ClassVar[deque[dict]] = deque()
    requests: ClassVar[list[dict]] = []

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length)
        try:
            StubModelHandler.requests.append(json.loads(body))
        except json.JSONDecodeError:
            StubModelHandler.requests.append({})
        if not StubModelHandler.responses:
            message = {"role": "assistant", "content": "默认回答"}
        else:
            message = StubModelHandler.responses.popleft()
        payload = {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        raw = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args: object) -> None:
        return


@pytest.fixture(scope="module")
def model_stub() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), StubModelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def reset_stub() -> None:
    StubModelHandler.responses.clear()
    StubModelHandler.requests.clear()


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _setup_agent(client: TestClient) -> dict:
    email = f"{_unique('agent')}@example.com"
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "display_name": "Agent Owner"},
    ).json()
    headers = {"Authorization": f"Bearer {registered['access_token']}"}
    tenant = client.post(
        "/api/v1/tenants", headers=headers, json={"name": _unique("Agent 企业")}
    ).json()
    tenant_headers = {**headers, "X-Tenant-ID": tenant["id"]}
    ai = client.post(
        "/api/v1/members",
        headers=tenant_headers,
        json={
            "member_type": "ai",
            "display_name": "CTO-AI",
            "title": "CTO",
            "role_keys": ["admin"],
        },
    ).json()
    agents = client.get("/api/v1/agents", headers=tenant_headers)
    assert agents.status_code == 200, agents.text
    agent = next(item for item in agents.json() if item["member_id"] == ai["id"])
    return {
        "token": registered["access_token"],
        "tenant_id": tenant["id"],
        "headers": tenant_headers,
        "agent": agent,
    }


def _create_session(client: TestClient, setup: dict, title: str = "架构评审") -> dict:
    response = client.post(
        f"/api/v1/agents/{setup['agent']['id']}/sessions",
        headers=setup["headers"],
        json={"title": title},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_run(
    client: TestClient, setup: dict, session_id: str, text_input: str, limits: dict | None = None
) -> dict:
    payload: dict = {"input": text_input}
    if limits is not None:
        payload["limits"] = limits
    response = client.post(
        f"/api/v1/sessions/{session_id}/runs", headers=setup["headers"], json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()


def _runtime_settings(model_stub: str) -> OrgWeaveSettings:
    return OrgWeaveSettings(litellm_base_url=model_stub, litellm_master_key="test-key")


async def _execute(settings: OrgWeaveSettings, tenant_id: str, run_id: str) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        async with factory() as session:
            await session.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"),
                {"t": tenant_id},
            )
            await execute_run(
                session,
                redis,
                settings,
                uuid.UUID(run_id),
                session_factory=factory,
            )
    finally:
        await redis.aclose()
        await engine.dispose()


def test_agent_auto_config_and_tool_loop(client: TestClient, model_stub: str) -> None:
    setup = _setup_agent(client)
    assert setup["agent"]["model_alias"] == "orgweave-default"
    assert "get_current_time" in setup["agent"]["allowed_tools"]
    assert setup["agent"]["max_steps"] == 8

    session = _create_session(client, setup)
    run = _create_run(client, setup, session["id"], "请告诉我当前时间并完成任务")

    StubModelHandler.responses.extend(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_time_1",
                        "type": "function",
                        "function": {"name": "get_current_time", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "assistant",
                "content": "任务完成：已获取当前时间并汇总结果。",
                "tool_calls": [],
            },
        ]
    )

    settings = _runtime_settings(model_stub)
    asyncio.run(_execute(settings, setup["tenant_id"], run["id"]))

    current = client.get(f"/api/v1/runs/{run['id']}", headers=setup["headers"])
    assert current.status_code == 200
    body = current.json()
    assert body["status"] == "completed", body
    assert body["steps"] == 2
    assert body["tool_calls_count"] == 1
    assert body["token_usage"] == 30
    assert "任务完成" in body["output"]

    tools = client.get(f"/api/v1/runs/{run['id']}/tools", headers=setup["headers"])
    assert tools.status_code == 200
    assert tools.json()[0]["tool_name"] == "get_current_time"
    assert tools.json()[0]["status"] == "completed"
    assert "utc" in tools.json()[0]["result"]

    messages = client.get(f"/api/v1/sessions/{session['id']}/messages", headers=setup["headers"])
    roles = [message["role"] for message in messages.json()]
    assert roles == ["user", "assistant", "tool", "assistant"]

    memories = client.get(
        f"/api/v1/agents/{setup['agent']['id']}/memories", headers=setup["headers"]
    )
    assert any(memory["memory_type"] == "episodic" for memory in memories.json())

    # The first model request must include the configured tools.
    assert StubModelHandler.requests
    assert StubModelHandler.requests[0]["model"] == "orgweave-default"
    assert StubModelHandler.requests[0]["tools"]


def test_max_steps_is_enforced(client: TestClient, model_stub: str) -> None:
    setup = _setup_agent(client)
    session = _create_session(client, setup, "限制测试")
    run = _create_run(client, setup, session["id"], "无限调用工具", limits={"max_steps": 2})

    for index in range(3):
        StubModelHandler.responses.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"call_{index}",
                        "type": "function",
                        "function": {"name": "get_current_time", "arguments": "{}"},
                    }
                ],
            }
        )

    asyncio.run(_execute(_runtime_settings(model_stub), setup["tenant_id"], run["id"]))
    body = client.get(f"/api/v1/runs/{run['id']}", headers=setup["headers"]).json()
    assert body["status"] == "failed"
    assert body["error"] == "max_steps_exceeded"
    assert body["steps"] == 2

    session_body = client.get(f"/api/v1/sessions/{session['id']}", headers=setup["headers"]).json()
    assert session_body["status"] == "failed"


def test_cancel_before_execution(client: TestClient, model_stub: str) -> None:
    setup = _setup_agent(client)
    session = _create_session(client, setup, "取消测试")
    run = _create_run(client, setup, session["id"], "这个任务会被取消")

    cancelled = client.post(f"/api/v1/runs/{run['id']}/cancel", headers=setup["headers"])
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    asyncio.run(_execute(_runtime_settings(model_stub), setup["tenant_id"], run["id"]))
    body = client.get(f"/api/v1/runs/{run['id']}", headers=setup["headers"]).json()
    assert body["status"] == "cancelled"


def test_model_gateway_failure_is_recorded(client: TestClient) -> None:
    setup = _setup_agent(client)
    session = _create_session(client, setup, "失败测试")
    run = _create_run(client, setup, session["id"], "触发模型错误")

    dead_settings = OrgWeaveSettings(
        litellm_base_url="http://127.0.0.1:1", litellm_master_key="test"
    )
    asyncio.run(_execute(dead_settings, setup["tenant_id"], run["id"]))
    body = client.get(f"/api/v1/runs/{run['id']}", headers=setup["headers"]).json()
    assert body["status"] == "failed"
    assert "模型网关不可用" in (body["error"] or "")


def test_sessions_are_isolated(client: TestClient, model_stub: str) -> None:
    setup = _setup_agent(client)
    first = _create_session(client, setup, "会话 A")
    second = _create_session(client, setup, "会话 B")

    StubModelHandler.responses.append(
        {"role": "assistant", "content": "A 的回答", "tool_calls": []}
    )
    run_a = _create_run(client, setup, first["id"], "A 的输入")
    asyncio.run(_execute(_runtime_settings(model_stub), setup["tenant_id"], run_a["id"]))

    StubModelHandler.responses.append(
        {"role": "assistant", "content": "B 的回答", "tool_calls": []}
    )
    run_b = _create_run(client, setup, second["id"], "B 的输入")
    asyncio.run(_execute(_runtime_settings(model_stub), setup["tenant_id"], run_b["id"]))

    messages_a = client.get(
        f"/api/v1/sessions/{first['id']}/messages", headers=setup["headers"]
    ).json()
    messages_b = client.get(
        f"/api/v1/sessions/{second['id']}/messages", headers=setup["headers"]
    ).json()
    assert [message["content"] for message in messages_a] == ["A 的输入", "A 的回答"]
    assert [message["content"] for message in messages_b] == ["B 的输入", "B 的回答"]


def test_cancel_key_is_consumed_by_runtime(client: TestClient) -> None:
    setup = _setup_agent(client)
    session = _create_session(client, setup, "取消键")
    run = _create_run(client, setup, session["id"], "不应执行")

    async def seed() -> None:
        settings = OrgWeaveSettings()
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            await redis.set(CANCEL_KEY.format(run_id=run["id"]), "1", ex=60)
        finally:
            await redis.aclose()

    asyncio.run(seed())
    asyncio.run(_execute(_runtime_settings("http://127.0.0.1:1"), setup["tenant_id"], run["id"]))
    body = client.get(f"/api/v1/runs/{run['id']}", headers=setup["headers"]).json()
    assert body["status"] in {"cancelled", "failed"}


def test_agent_worker_processes_queued_job(client: TestClient, model_stub: str) -> None:
    """The Agent Worker adapter executes a queued agent.run job end-to-end."""
    from orgweave_agent_sdk import AgentJob
    from orgweave_agent_worker.runner import handle_agent_run
    from sqlalchemy.ext.asyncio import async_sessionmaker

    setup = _setup_agent(client)
    session = _create_session(client, setup, "Worker 集成")
    run = _create_run(client, setup, session["id"], "worker 处理这条任务")
    StubModelHandler.responses.append(
        {"role": "assistant", "content": "Worker 执行完成", "tool_calls": []}
    )

    settings = _runtime_settings(model_stub)

    async def process() -> None:
        engine = create_async_engine(settings.database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            job = AgentJob(
                type="agent.run",
                payload={
                    "run_id": run["id"],
                    "session_id": session["id"],
                    "tenant_id": setup["tenant_id"],
                },
            )
            await handle_agent_run(redis, settings, factory, job)
        finally:
            await redis.aclose()
            await engine.dispose()

    asyncio.run(process())
    body = client.get(f"/api/v1/runs/{run['id']}", headers=setup["headers"]).json()
    assert body["status"] == "completed", body
    assert body["output"] == "Worker 执行完成"


def _setup_two_agents(client: TestClient) -> dict:
    email = f"{_unique('deleg')}@example.com"
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "display_name": "Delegation Owner"},
    ).json()
    headers = {"Authorization": f"Bearer {registered['access_token']}"}
    tenant = client.post(
        "/api/v1/tenants", headers=headers, json={"name": _unique("委派企业")}
    ).json()
    tenant_headers = {**headers, "X-Tenant-ID": tenant["id"]}
    for name, title in (("CTO-AI", "CTO"), ("Researcher-AI", "研究员")):
        response = client.post(
            "/api/v1/members",
            headers=tenant_headers,
            json={
                "member_type": "ai",
                "display_name": name,
                "title": title,
                "role_keys": ["admin"],
            },
        )
        assert response.status_code == 201, response.text
    agents = client.get("/api/v1/agents", headers=tenant_headers).json()
    by_name = {agent["member_name"]: agent for agent in agents}
    return {
        "headers": tenant_headers,
        "tenant_id": tenant["id"],
        "cto": by_name["CTO-AI"],
        "researcher": by_name["Researcher-AI"],
    }


def test_synchronous_delegation_creates_child_session_and_returns_result(
    client: TestClient, model_stub: str
) -> None:
    setup = _setup_two_agents(client)
    session = client.post(
        f"/api/v1/agents/{setup['cto']['id']}/sessions",
        headers=setup["headers"],
        json={"title": "CTO 项目会话"},
    ).json()
    run = _create_run(client, setup, session["id"], "请把需求调研委派给 Researcher")

    StubModelHandler.responses.extend(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_delegate_1",
                        "type": "function",
                        "function": {
                            "name": "delegate_task",
                            "arguments": json.dumps(
                                {
                                    "agent_id": setup["researcher"]["id"],
                                    "task": "调研 IT 资产管理的核心需求",
                                    "wait": True,
                                }
                            ),
                        },
                    }
                ],
            },
            {
                "role": "assistant",
                "content": "调研完成：需要资产台账、生命周期与审计。",
                "tool_calls": [],
            },
            {
                "role": "assistant",
                "content": "CTO 汇总：已收到调研结果，项目可以启动。",
                "tool_calls": [],
            },
        ]
    )

    asyncio.run(_execute(_runtime_settings(model_stub), setup["tenant_id"], run["id"]))

    body = client.get(f"/api/v1/runs/{run['id']}", headers=setup["headers"]).json()
    assert body["status"] == "completed", body
    assert "CTO 汇总" in body["output"]

    tools = client.get(f"/api/v1/runs/{run['id']}/tools", headers=setup["headers"]).json()
    assert len(tools) == 1
    assert tools[0]["tool_name"] == "delegate_task"
    assert tools[0]["status"] == "completed"
    assert tools[0]["result"]["status"] == "completed"

    delegations = client.get(
        f"/api/v1/sessions/{session['id']}/delegations", headers=setup["headers"]
    ).json()
    assert len(delegations) == 1
    delegation = delegations[0]
    assert delegation["status"] == "completed"
    assert delegation["child_agent_id"] == setup["researcher"]["id"]
    assert "资产台账" in (delegation["summary"] or "")

    children = client.get(
        f"/api/v1/sessions/{session['id']}/children", headers=setup["headers"]
    ).json()
    assert len(children) == 1
    assert children[0]["id"] == delegation["child_session_id"]
    assert children[0]["parent_session_id"] == session["id"]

    child_messages = client.get(
        f"/api/v1/sessions/{delegation['child_session_id']}/messages",
        headers=setup["headers"],
    ).json()
    assert any(
        message["role"] == "assistant" and "资产台账" in message["content"]
        for message in child_messages
    )

    parent_messages = client.get(
        f"/api/v1/sessions/{session['id']}/messages", headers=setup["headers"]
    ).json()
    assert any(
        message["role"] == "system" and "子 Agent" in message["content"]
        for message in parent_messages
    )


def test_delegation_permission_is_server_enforced(client: TestClient, model_stub: str) -> None:
    setup = _setup_two_agents(client)
    denied = client.patch(
        f"/api/v1/agents/{setup['cto']['id']}",
        headers=setup["headers"],
        json={"allowed_agent_ids": []},
    )
    assert denied.status_code == 200, denied.text

    session = client.post(
        f"/api/v1/agents/{setup['cto']['id']}/sessions",
        headers=setup["headers"],
        json={"title": "越权委派"},
    ).json()
    run = _create_run(client, setup, session["id"], "尝试越权委派")
    StubModelHandler.responses.extend(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_delegate_denied",
                        "type": "function",
                        "function": {
                            "name": "delegate_task",
                            "arguments": json.dumps(
                                {
                                    "agent_id": setup["researcher"]["id"],
                                    "task": "越权任务",
                                }
                            ),
                        },
                    }
                ],
            },
            {"role": "assistant", "content": "无法委派。", "tool_calls": []},
        ]
    )
    asyncio.run(_execute(_runtime_settings(model_stub), setup["tenant_id"], run["id"]))

    tools = client.get(f"/api/v1/runs/{run['id']}/tools", headers=setup["headers"]).json()
    assert tools[0]["status"] == "failed"
    assert "无权委派" in (tools[0]["error"] or "")
    delegations = client.get(
        f"/api/v1/sessions/{session['id']}/delegations", headers=setup["headers"]
    ).json()
    assert delegations == []


def test_async_delegation_is_queued_and_finalized(client: TestClient, model_stub: str) -> None:
    from orgweave_agent_sdk import AgentJob
    from orgweave_agent_worker.runner import handle_agent_run
    from sqlalchemy.ext.asyncio import async_sessionmaker

    setup = _setup_two_agents(client)
    session = client.post(
        f"/api/v1/agents/{setup['cto']['id']}/sessions",
        headers=setup["headers"],
        json={"title": "异步委派"},
    ).json()
    run = _create_run(client, setup, session["id"], "异步委派调研")
    StubModelHandler.responses.extend(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_delegate_async",
                        "type": "function",
                        "function": {
                            "name": "delegate_task",
                            "arguments": json.dumps(
                                {
                                    "agent_id": setup["researcher"]["id"],
                                    "task": "异步调研任务",
                                    "wait": False,
                                }
                            ),
                        },
                    }
                ],
            },
            {"role": "assistant", "content": "已异步委派。", "tool_calls": []},
        ]
    )
    asyncio.run(_execute(_runtime_settings(model_stub), setup["tenant_id"], run["id"]))
    delegations = client.get(
        f"/api/v1/sessions/{session['id']}/delegations", headers=setup["headers"]
    ).json()
    assert delegations[0]["status"] == "queued"
    delegation = delegations[0]

    StubModelHandler.responses.append(
        {"role": "assistant", "content": "异步调研结果", "tool_calls": []}
    )
    settings = _runtime_settings(model_stub)

    async def process_child() -> None:
        engine = create_async_engine(settings.database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            job = AgentJob(
                type="agent.run",
                payload={
                    "run_id": delegation["child_run_id"],
                    "session_id": delegation["child_session_id"],
                    "tenant_id": setup["tenant_id"],
                },
            )
            await handle_agent_run(redis, settings, factory, job)
        finally:
            await redis.aclose()
            await engine.dispose()

    asyncio.run(process_child())
    updated = client.get(f"/api/v1/delegations/{delegation['id']}", headers=setup["headers"]).json()
    assert updated["status"] == "completed"
    assert updated["summary"] == "异步调研结果"
