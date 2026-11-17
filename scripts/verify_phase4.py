#!/usr/bin/env python3
"""Phase 4 acceptance: authorized delegation, child session and real result exchange."""

from __future__ import annotations

import os
import sys
import time
import uuid

import httpx

API = f"http://localhost:{os.environ.get('API_PORT', '8000')}"
WEB = "http://localhost:3000"
PASSWORD = "correct-horse-battery"


def main() -> int:
    client = httpx.Client(timeout=30)
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))
        print(f"  {'PASS' if ok else 'FAIL'} {name}{(' — ' + detail) if detail and not ok else ''}")

    email = f"phase4-{uuid.uuid4().hex[:8]}@example.com"
    register = client.post(
        f"{API}/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "display_name": "委派验收"},
    )
    register.raise_for_status()
    headers = {"Authorization": f"Bearer {register.json()['access_token']}"}
    tenant = client.post(
        f"{API}/api/v1/tenants",
        headers=headers,
        json={"name": f"委派验收-{uuid.uuid4().hex[:6]}"},
    )
    tenant.raise_for_status()
    tenant_id = tenant.json()["id"]
    th = {**headers, "X-Tenant-ID": tenant_id}

    for name, title in (("CTO-AI", "CTO"), ("Researcher-AI", "研究员")):
        response = client.post(
            f"{API}/api/v1/members",
            headers=th,
            json={
                "member_type": "ai",
                "display_name": name,
                "title": title,
                "role_keys": ["admin"],
            },
        )
        response.raise_for_status()
    agents = {item["member_name"]: item for item in client.get(f"{API}/api/v1/agents", headers=th).json()}
    cto = agents.get("CTO-AI")
    researcher = agents.get("Researcher-AI")
    check("two agent configs", bool(cto and researcher))
    if not cto or not researcher:
        return 1
    check(
        "delegation tools enabled",
        "delegate_task" in cto["allowed_tools"],
        str(cto["allowed_tools"]),
    )
    check("allowed agents default all", cto["allowed_agent_ids"] == ["*"])

    session = client.post(
        f"{API}/api/v1/agents/{cto['id']}/sessions",
        headers=th,
        json={"title": "Phase 4 验收会话"},
    ).json()
    prompt = (
        f"请立即调用 delegate_task 工具委派任务。参数：agent_id=\"{researcher['id']}\"，"
        'task="调研 IT 资产管理系统需要哪些核心模块，并给出三条建议"，wait=true。'
        "收到子 Agent 结果后，用中文给出一段总结。不要省略工具调用。"
    )
    run_response = client.post(
        f"{API}/api/v1/sessions/{session['id']}/runs",
        headers=th,
        json={"input": prompt, "limits": {"max_steps": 6, "max_duration_seconds": 240}},
    )
    run_response.raise_for_status()
    run = run_response.json()
    print(f"  run={run['id']} session={session['id']}")

    deadline = time.monotonic() + 300
    body = run
    while body["status"] in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(2)
        body = client.get(f"{API}/api/v1/runs/{run['id']}", headers=th).json()
    check("parent run completed", body["status"] == "completed", f"{body['status']}: {body.get('error')}")
    check("parent used delegation", body["tool_calls_count"] >= 1)

    tools = client.get(f"{API}/api/v1/runs/{run['id']}/tools", headers=th).json()
    delegation_tools = [tool for tool in tools if tool["tool_name"] == "delegate_task"]
    check("delegate_task executed", bool(delegation_tools) and delegation_tools[0]["status"] == "completed")

    delegations = client.get(
        f"{API}/api/v1/sessions/{session['id']}/delegations", headers=th
    ).json()
    check("delegation persisted", len(delegations) == 1)
    if delegations:
        delegation = delegations[0]
        check("delegation completed", delegation["status"] == "completed")
        check("child agent correct", delegation["child_agent_id"] == researcher["id"])
        check("result returned", bool(delegation["summary"]))
        child_messages = client.get(
            f"{API}/api/v1/sessions/{delegation['child_session_id']}/messages",
            headers=th,
        ).json()
        check("child session has independent messages", len(child_messages) >= 2)
        children = client.get(
            f"{API}/api/v1/sessions/{session['id']}/children", headers=th
        ).json()
        check("child session linked to parent", len(children) == 1 and children[0]["parent_session_id"] == session["id"])

    web = client.get(f"{WEB}/workspace")
    check("workspace web page", web.status_code == 200)

    passed = sum(1 for _, ok, _ in checks if ok)
    failed = len(checks) - passed
    print("----------------------------------------")
    print(f"Phase 4 verification: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
