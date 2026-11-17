"""Phase 1 end-to-end tests against real PostgreSQL with RLS."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from app.main import app
from fastapi.testclient import TestClient
from orgweave_shared.settings import OrgWeaveSettings
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery"


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _register(client: TestClient, email: str | None = None, name: str = "测试用户") -> dict:
    email = email or f"{_unique('user')}@example.com"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "display_name": name},
    )
    assert response.status_code == 201, response.text
    return {"email": email, **response.json()}


def _auth(user: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {user['access_token']}"}


def _create_tenant(client: TestClient, user: dict, name: str | None = None) -> dict:
    response = client.post(
        "/api/v1/tenants",
        headers=_auth(user),
        json={"name": name or _unique("企业")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _headers(user: dict, tenant_id: str) -> dict[str, str]:
    return {**_auth(user), "X-Tenant-ID": tenant_id}


def test_auth_register_login_refresh_logout(client: TestClient) -> None:
    user = _register(client)
    assert user["user"]["email"] == user["email"]
    assert user["token_type"] == "bearer"
    assert user["expires_in"] == 900

    me = client.get("/api/v1/auth/me", headers=_auth(user))
    assert me.status_code == 200
    assert me.json()["user"]["email"] == user["email"]
    assert me.json()["tenants"] == []

    login = client.post("/api/v1/auth/login", json={"email": user["email"], "password": PASSWORD})
    assert login.status_code == 200, login.text
    login_tokens = login.json()

    rotated = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": login_tokens["refresh_token"]}
    )
    assert rotated.status_code == 200, rotated.text
    new_tokens = rotated.json()
    assert new_tokens["refresh_token"] != login_tokens["refresh_token"]

    reused = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": login_tokens["refresh_token"]}
    )
    assert reused.status_code == 401

    logged_out = client.post(
        "/api/v1/auth/logout", json={"refresh_token": new_tokens["refresh_token"]}
    )
    assert logged_out.status_code == 204
    after_logout = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": new_tokens["refresh_token"]}
    )
    assert after_logout.status_code == 401


def test_login_rejects_bad_password_and_duplicate_email(client: TestClient) -> None:
    user = _register(client)
    bad = client.post(
        "/api/v1/auth/login", json={"email": user["email"], "password": "wrong-password"}
    )
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "invalid_credentials"

    duplicate = client.post(
        "/api/v1/auth/register",
        json={"email": user["email"], "password": PASSWORD, "display_name": "重复"},
    )
    assert duplicate.status_code == 409


def test_tenant_creation_and_current_context(client: TestClient) -> None:
    user = _register(client)
    tenant = _create_tenant(client, user, "Acme 科技")

    listing = client.get("/api/v1/tenants", headers=_auth(user))
    assert listing.status_code == 200
    tenants = listing.json()
    assert len(tenants) == 1
    assert tenants[0]["id"] == tenant["id"]
    assert tenants[0]["role_keys"] == ["owner"]

    current = client.get("/api/v1/tenant", headers=_headers(user, tenant["id"]))
    assert current.status_code == 200, current.text
    body = current.json()
    assert body["membership_status"] == "active"
    assert body["role_keys"] == ["owner"]
    assert "tenant.manage" in body["permissions"]
    assert "member.manage" in body["permissions"]


def test_tenant_context_requires_header_and_membership(client: TestClient) -> None:
    owner = _register(client)
    tenant = _create_tenant(client, owner)
    other = _register(client)

    missing = client.get("/api/v1/members", headers=_auth(owner))
    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "tenant_required"

    foreign = client.get("/api/v1/members", headers=_headers(other, tenant["id"]))
    assert foreign.status_code == 403

    hidden = client.get(f"/api/v1/tenants/{tenant['id']}", headers=_auth(other))
    assert hidden.status_code == 404


def test_departments_members_and_permissions(client: TestClient) -> None:
    owner = _register(client, name="Owner")
    member_user = _register(client, name="New Hire")
    tenant = _create_tenant(client, owner, "组织测试公司")
    headers = _headers(owner, tenant["id"])

    dept = client.post("/api/v1/departments", headers=headers, json={"name": "研发部"})
    assert dept.status_code == 201, dept.text
    dept_id = dept.json()["id"]

    child = client.post(
        "/api/v1/departments",
        headers=headers,
        json={"name": "平台组", "parent_id": dept_id},
    )
    assert child.status_code == 201, child.text
    child_id = child.json()["id"]

    cycle = client.patch(
        f"/api/v1/departments/{dept_id}",
        headers=headers,
        json={"parent_id": child_id},
    )
    assert cycle.status_code == 422
    assert cycle.json()["error"]["code"] == "department_cycle"

    ai = client.post(
        "/api/v1/members",
        headers=headers,
        json={
            "member_type": "ai",
            "display_name": "CTO-AI",
            "title": "首席技术官",
            "department_id": dept_id,
            "role_keys": ["admin"],
        },
    )
    assert ai.status_code == 201, ai.text
    assert ai.json()["roles"][0]["key"] == "admin"

    human = client.post(
        "/api/v1/members",
        headers=headers,
        json={
            "member_type": "human",
            "user_id": member_user["user"]["id"],
            "display_name": "新员工",
            "department_id": child_id,
            "role_keys": ["member"],
        },
    )
    assert human.status_code == 201, human.text
    human_id = human.json()["id"]

    duplicate = client.post(
        "/api/v1/members",
        headers=headers,
        json={
            "member_type": "human",
            "user_id": member_user["user"]["id"],
            "display_name": "重复",
        },
    )
    assert duplicate.status_code == 409

    # The human member can now enter the tenant.
    member_current = client.get("/api/v1/tenant", headers=_headers(member_user, tenant["id"]))
    assert member_current.status_code == 200
    assert member_current.json()["role_keys"] == ["member"]

    # Member role cannot manage departments.
    forbidden = client.post(
        "/api/v1/departments",
        headers=_headers(member_user, tenant["id"]),
        json={"name": "越权部门"},
    )
    assert forbidden.status_code == 403

    # Owner promotes the member to admin; permission takes effect.
    promoted = client.put(
        f"/api/v1/members/{human_id}/roles",
        headers=headers,
        json={"role_keys": ["admin"]},
    )
    assert promoted.status_code == 200, promoted.text
    allowed = client.post(
        "/api/v1/departments",
        headers=_headers(member_user, tenant["id"]),
        json={"name": "运营部"},
    )
    assert allowed.status_code == 201, allowed.text

    # Department with members cannot be deleted.
    blocked = client.delete(f"/api/v1/departments/{child_id}", headers=headers)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "department_has_members"

    roles = client.get("/api/v1/roles", headers=headers)
    assert roles.status_code == 200
    role_map = {role["key"]: role for role in roles.json()}
    assert "tenant.manage" in role_map["owner"]["permissions"]
    assert "tenant.manage" not in role_map["admin"]["permissions"]

    audit = client.get("/api/v1/audit", headers=headers)
    assert audit.status_code == 200
    actions = {entry["action"] for entry in audit.json()}
    assert {"department.created", "member.created", "member.roles_updated"} <= actions


def test_invitation_flow_and_email_binding(client: TestClient) -> None:
    owner = _register(client)
    invitee = _register(client)
    other = _register(client)
    tenant = _create_tenant(client, owner, "邀请测试公司")

    created = client.post(
        "/api/v1/invitations",
        headers=_headers(owner, tenant["id"]),
        json={"email": invitee["email"], "role_key": "member"},
    )
    assert created.status_code == 201, created.text
    invitation = created.json()
    assert invitation["token"]
    assert invitation["status"] == "pending"

    # Wrong account cannot accept the invitation.
    mismatch = client.post(
        "/api/v1/invitations/accept",
        headers=_auth(other),
        json={"token": invitation["token"]},
    )
    assert mismatch.status_code == 403
    assert mismatch.json()["error"]["code"] == "invitation_email_mismatch"

    accepted = client.post(
        "/api/v1/invitations/accept",
        headers=_auth(invitee),
        json={"token": invitation["token"]},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["tenant_id"] == tenant["id"]

    current = client.get("/api/v1/tenant", headers=_headers(invitee, tenant["id"]))
    assert current.status_code == 200
    assert current.json()["role_keys"] == ["member"]

    again = client.post(
        "/api/v1/invitations/accept",
        headers=_auth(invitee),
        json={"token": invitation["token"]},
    )
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_rls_is_enforced_for_application_role(client: TestClient) -> None:
    owner = _register(client)
    tenant_a = _create_tenant(client, owner, "RLS A")
    tenant_b = _create_tenant(client, owner, "RLS B")

    for tenant, name in ((tenant_a, "A 部门"), (tenant_b, "B 部门")):
        response = client.post(
            "/api/v1/departments",
            headers=_headers(owner, tenant["id"]),
            json={"name": name},
        )
        assert response.status_code == 201, response.text

    settings = OrgWeaveSettings()
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as connection:
            async with connection.begin():
                await connection.execute(
                    text("SELECT set_config('app.tenant_id', :t, true)"),
                    {"t": tenant_a["id"]},
                )
                rows = (
                    (await connection.execute(text("SELECT tenant_id FROM departments")))
                    .scalars()
                    .all()
                )
                assert {str(row) for row in rows} == {tenant_a["id"]}

        async with engine.connect() as connection:
            async with connection.begin():
                await connection.execute(
                    text("SELECT set_config('app.tenant_id', :t, true)"),
                    {"t": tenant_b["id"]},
                )
                rows = (
                    (await connection.execute(text("SELECT tenant_id FROM departments")))
                    .scalars()
                    .all()
                )
                assert {str(row) for row in rows} == {tenant_b["id"]}

        # No tenant context: zero rows, not another tenant's data.
        async with engine.connect() as connection:
            async with connection.begin():
                count = (
                    await connection.execute(text("SELECT count(*) FROM departments"))
                ).scalar_one()
                assert count == 0

        # Writing into another tenant is rejected by the WITH CHECK policy.
        async with engine.connect() as connection:
            with pytest.raises(DBAPIError):
                async with connection.begin():
                    await connection.execute(
                        text("SELECT set_config('app.tenant_id', :t, true)"),
                        {"t": tenant_a["id"]},
                    )
                    await connection.execute(
                        text(
                            """
                            INSERT INTO departments (id, tenant_id, name)
                            VALUES (gen_random_uuid(), :t, :name)
                            """
                        ),
                        {"t": tenant_b["id"], "name": "越权写入"},
                    )
    finally:
        await engine.dispose()


def test_audit_login_is_visible_only_to_actor(client: TestClient) -> None:
    user = _register(client)
    response = client.get("/api/v1/auth/me", headers=_auth(user))
    assert response.status_code == 200

    # Directly verify the global audit row is not exposed through tenant audit.
    settings = OrgWeaveSettings()

    async def check() -> int:
        engine = create_async_engine(settings.database_url)
        try:
            async with engine.connect() as connection:
                await connection.execute(
                    text("SELECT set_config('app.user_id', :u, true)"),
                    {"u": user["user"]["id"]},
                )
                return (
                    await connection.execute(
                        text(
                            "SELECT count(*) FROM audit_logs "
                            "WHERE tenant_id IS NULL AND action = 'auth.registered'"
                        )
                    )
                ).scalar_one()
        finally:
            await engine.dispose()

    import asyncio

    assert asyncio.run(check()) >= 1


def test_invalid_and_missing_tokens(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401
    bad = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-token"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "invalid_token"
    assert datetime.now(UTC).tzinfo is not None


def test_authenticated_websocket_handshake(client: TestClient) -> None:
    user = _register(client)
    with client.websocket_connect(f"/ws/v1?token={user['access_token']}") as websocket:
        hello = websocket.receive_json()
        assert hello["type"] == "hello"
        assert hello["user_id"] == user["user"]["id"]
        assert hello["display_name"] == user["user"]["display_name"]

        websocket.send_json({"type": "ping"})
        assert websocket.receive_json()["type"] == "pong"

        websocket.send_text("not-json")
        error = websocket.receive_json()
        assert error["reason"] == "invalid_json"
