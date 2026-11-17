#!/usr/bin/env python3
"""MVP checkpoint: CTO/Researcher/Developer/QA deliver and test real software."""

from __future__ import annotations

import io
import json
import os
import sys
import time
import uuid

import httpx

API = f"http://localhost:{os.environ.get('API_PORT', '8000')}"
PASSWORD = "correct-horse-battery"

SYSTEM_PROMPTS = {
    "CTO-AI": (
        "你是企业 CTO。你只负责规划和委派，不自己写代码。"
        "你必须在一次回复中或连续回复中调用 delegate_task 工具，依次把任务委派给 "
        "Researcher-AI、Developer-AI、QA-AI，并等待每个子任务完成后再汇总。"
    ),
    "Researcher-AI": (
        "你是需求研究员。请给出简洁、可执行的需求清单和验收标准，不要写代码。"
    ),
    "Developer-AI": (
        "你是开发工程师。你必须使用 workspace_write_file 把代码写入共享工作区："
        "asset_manager.py（实现资产增删查与状态统计）和 test_asset_manager.py"
        "（至少 3 个 pytest 用例）。完成后必须调用 run_tests，确认 exit_code=0，"
        "并在最终回答中报告测试输出。"
    ),
    "QA-AI": (
        "你是 QA 工程师。你必须调用 run_tests 执行共享工作区中的 pytest 测试，"
        "检查是否通过，并报告测试输出与风险。"
    ),
}


def main() -> int:
    client = httpx.Client(timeout=60)
    suffix = uuid.uuid4().hex[:8]
    register = client.post(
        f"{API}/api/v1/auth/register",
        json={
            "email": f"mvp-{suffix}@example.com",
            "password": PASSWORD,
            "display_name": "MVP Owner",
        },
    )
    register.raise_for_status()
    headers = {"Authorization": f"Bearer {register.json()['access_token']}"}
    tenant = client.post(
        f"{API}/api/v1/tenants",
        headers=headers,
        json={"name": f"MVP 软件公司-{suffix}"},
    )
    tenant.raise_for_status()
    tenant_id = tenant.json()["id"]
    th = {**headers, "X-Tenant-ID": tenant_id}

    for name, title in (
        ("CTO-AI", "CTO"),
        ("Researcher-AI", "需求研究员"),
        ("Developer-AI", "开发工程师"),
        ("QA-AI", "测试工程师"),
    ):
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
    model_aliases = {
        "CTO-AI": "orgweave-fast",
        "Researcher-AI": "orgweave-fast",
        "Developer-AI": "orgweave-strong",
        "QA-AI": "orgweave-fast",
    }
    for name, prompt in SYSTEM_PROMPTS.items():
        agent = agents[name]
        response = client.patch(
            f"{API}/api/v1/agents/{agent['id']}",
            headers=th,
            json={
                "system_prompt": prompt,
                "max_steps": 10,
                "max_duration_seconds": 600,
                "token_budget": 60000,
                "max_tool_calls": 20,
                "max_output_tokens": 1200,
                "model_alias": model_aliases[name],
            },
        )
        response.raise_for_status()
        agents[name] = response.json()

    cto = agents["CTO-AI"]
    session = client.post(
        f"{API}/api/v1/agents/{cto['id']}/sessions",
        headers=th,
        json={"title": "MVP：IT 资产管理系统"},
    ).json()

    prompt = f"""
项目：开发一个最小可运行的 IT 资产管理系统核心模块（Python）。

你必须严格按顺序完成三步，每一步都调用 delegate_task 工具（wait=true），
收到结果后再进行下一步，最后汇总全部结果：

第 1 步 — 委派给 Researcher-AI：
  agent_id="{agents['Researcher-AI']['id']}"
  task="为 IT 资产管理系统给出核心功能需求清单和验收标准，简洁输出。"

第 2 步 — 委派给 Developer-AI：
  agent_id="{agents['Developer-AI']['id']}"
  task="立即调用工具，不要输出计划。用 workspace_write_file 创建两个文件：1) asset_manager.py：一个 AssetManager 类，支持 add(name,status)、get(name)、count_by_status()；2) test_asset_manager.py：3 个 pytest 用例覆盖新增、查询、统计。然后调用 run_tests，确认 exit_code=0，并汇报测试输出。"

第 3 步 — 委派给 QA-AI：
  agent_id="{agents['QA-AI']['id']}"
  task="使用 run_tests 执行共享工作区测试，报告是否通过、输出摘要和风险。"

最后用中文汇总：需求、实现文件、测试结果、交付结论。
"""
    run_response = client.post(
        f"{API}/api/v1/sessions/{session['id']}/runs",
        headers=th,
        json={
            "input": prompt,
            "limits": {
                "max_steps": 12,
                "max_duration_seconds": 600,
                "token_budget": 80000,
                "max_tool_calls": 20,
                "model_alias": "orgweave-strong",
            },
        },
    )
    run_response.raise_for_status()
    run = run_response.json()
    print(f"run={run['id']} session={session['id']} tenant={tenant_id}")

    deadline = time.monotonic() + 420
    body = run
    while body["status"] in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(3)
        body = client.get(f"{API}/api/v1/runs/{run['id']}", headers=th).json()

    print("RUN_STATUS", body["status"], "steps", body["steps"], "tools", body["tool_calls_count"], "tokens", body["token_usage"])
    if body.get("error"):
        print("RUN_ERROR", body["error"])
    print("RUN_OUTPUT", (body.get("output") or "")[:2000])

    delegations = client.get(
        f"{API}/api/v1/sessions/{session['id']}/delegations", headers=th
    ).json()
    print("DELEGATIONS", [(d["status"], d["child_agent_id"], (d["summary"] or "")[:120]) for d in delegations])

    tools = client.get(f"{API}/api/v1/runs/{run['id']}/tools", headers=th).json()
    print("CTO_TOOLS", [(t["tool_name"], t["status"]) for t in tools])

    # Inspect the shared workspace through MinIO directly.
    import io

    from minio import Minio

    settings = httpx.get("http://localhost:8000/api/v1/health/live").json()
    minio = Minio(
        "localhost:9000",
        access_key=os.environ.get("S3_ACCESS_KEY", "orgweave"),
        secret_key=os.environ.get("S3_SECRET_KEY", "orgweave_dev_minio_password"),
        secure=False,
    )
    bucket = os.environ.get("MINIO_BUCKET", "orgweave")
    prefix = f"agent-workspaces/{tenant_id}/"
    files = [
        item.object_name
        for item in minio.list_objects(bucket, prefix=prefix, recursive=True)
        if not item.is_dir
    ]
    print("WORKSPACE_FILES", files)
    for key in files:
        response = minio.get_object(bucket, key)
        try:
            content = response.read().decode("utf-8", errors="replace")
        finally:
            response.close()
        print(f"FILE {key} ({len(content)} bytes)")
        print(content[:1200])

    completed = (
        body["status"] == "completed"
        and len(delegations) >= 3
        and all(delegation["status"] == "completed" for delegation in delegations)
        and any(key.endswith("asset_manager.py") for key in files)
        and any(key.endswith("test_asset_manager.py") for key in files)
    )
    print("MVP", "PASS" if completed else "FAIL")
    return 0 if completed else 1


if __name__ == "__main__":
    sys.exit(main())
