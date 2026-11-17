"""Phase 2 chat, mentions, attachments and realtime tests."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Iterator

import pytest
from app.application.chat import event_channel
from app.main import app
from fastapi.testclient import TestClient
from orgweave_shared.settings import OrgWeaveSettings
from redis.asyncio import Redis

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery"


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _register(client: TestClient, name: str = "聊天用户") -> dict:
    email = f"{_unique('chat')}@example.com"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "display_name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _auth(user: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {user['access_token']}"}


def _tenant(client: TestClient, user: dict) -> str:
    response = client.post(
        "/api/v1/tenants",
        headers=_auth(user),
        json={"name": _unique("聊天企业")},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _headers(user: dict, tenant_id: str) -> dict[str, str]:
    return {**_auth(user), "X-Tenant-ID": tenant_id}


def _create_member(
    client: TestClient,
    user: dict,
    tenant_id: str,
    *,
    name: str,
    member_type: str = "human",
    target_user: dict | None = None,
) -> dict:
    payload: dict = {
        "member_type": member_type,
        "display_name": name,
        "role_keys": ["member"],
    }
    if member_type == "human":
        assert target_user is not None
        payload["user_id"] = target_user["user"]["id"]
    response = client.post("/api/v1/members", headers=_headers(user, tenant_id), json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_group_creation_direct_dedupe_and_isolation(client: TestClient) -> None:
    owner = _register(client, "Owner")
    human = _register(client, "Human 2")
    outsider = _register(client, "Outsider")
    tenant_id = _tenant(client, owner)

    ai = _create_member(client, owner, tenant_id, name="AI CTO", member_type="ai")
    human_member = _create_member(client, owner, tenant_id, name="Human 2", target_user=human)
    outsider_member = _create_member(
        client, owner, tenant_id, name="Outsider", target_user=outsider
    )

    channel = client.post(
        "/api/v1/groups",
        headers=_headers(owner, tenant_id),
        json={
            "name": "产品研发群",
            "group_type": "channel",
            "member_ids": [ai["id"], human_member["id"]],
        },
    )
    assert channel.status_code == 201, channel.text
    channel_body = channel.json()
    assert channel_body["group_type"] == "channel"
    assert len(channel_body["members"]) == 3
    assert any(member["role"] == "owner" for member in channel_body["members"])
    channel_id = channel_body["id"]

    direct = client.post(
        "/api/v1/groups",
        headers=_headers(owner, tenant_id),
        json={"group_type": "direct", "member_ids": [human_member["id"]]},
    )
    assert direct.status_code == 201, direct.text
    direct_id = direct.json()["id"]
    direct_again = client.post(
        "/api/v1/groups",
        headers=_headers(owner, tenant_id),
        json={"group_type": "direct", "member_ids": [human_member["id"]]},
    )
    assert direct_again.json()["id"] == direct_id

    groups = client.get("/api/v1/groups", headers=_headers(owner, tenant_id))
    assert groups.status_code == 200
    assert len(groups.json()) == 2

    # Tenant member outside the group cannot list it or read messages.
    outsider_groups = client.get("/api/v1/groups", headers=_headers(outsider, tenant_id))
    assert outsider_groups.status_code == 200
    assert outsider_groups.json() == []
    denied = client.get(
        f"/api/v1/groups/{channel_id}/messages",
        headers=_headers(outsider, tenant_id),
    )
    assert denied.status_code == 404
    denied_send = client.post(
        f"/api/v1/groups/{channel_id}/messages",
        headers=_headers(outsider, tenant_id),
        json={"content": "越权消息"},
    )
    assert denied_send.status_code == 404

    # Group owner adds the outsider; now access works.
    added = client.post(
        f"/api/v1/groups/{channel_id}/members",
        headers=_headers(owner, tenant_id),
        json={"member_ids": [outsider_member["id"]]},
    )
    assert added.status_code == 200, added.text
    assert len(added.json()["members"]) == 4
    allowed = client.get(
        f"/api/v1/groups/{channel_id}/messages",
        headers=_headers(outsider, tenant_id),
    )
    assert allowed.status_code == 200


def test_messages_mentions_threads_search_and_read(client: TestClient) -> None:
    owner = _register(client, "Owner")
    human = _register(client, "Reader")
    tenant_id = _tenant(client, owner)
    ai = _create_member(client, owner, tenant_id, name="AI CTO", member_type="ai")
    human_member = _create_member(client, owner, tenant_id, name="Reader", target_user=human)

    group = client.post(
        "/api/v1/groups",
        headers=_headers(owner, tenant_id),
        json={"name": "讨论群", "member_ids": [ai["id"], human_member["id"]]},
    ).json()
    group_id = group["id"]

    first = client.post(
        f"/api/v1/groups/{group_id}/messages",
        headers=_headers(owner, tenant_id),
        json={"content": "请 @AI CTO 评估这个方案"},
    )
    assert first.status_code == 201, first.text
    first_body = first.json()
    assert {mention["id"] for mention in first_body["mentions"]} == {ai["id"]}
    assert "@AI CTO" in first_body["content"]

    reply = client.post(
        f"/api/v1/groups/{group_id}/messages",
        headers=_headers(owner, tenant_id),
        json={
            "content": "补充一个线程回复",
            "parent_message_id": first_body["id"],
            "mention_member_ids": [human_member["id"]],
        },
    )
    assert reply.status_code == 201, reply.text
    assert reply.json()["parent_message_id"] == first_body["id"]
    assert reply.json()["mentions"][0]["id"] == human_member["id"]

    history = client.get(f"/api/v1/groups/{group_id}/messages", headers=_headers(owner, tenant_id))
    assert history.status_code == 200
    assert [item["id"] for item in history.json()] == [
        first_body["id"],
        reply.json()["id"],
    ]

    search = client.get(
        f"/api/v1/groups/{group_id}/messages?search=方案",
        headers=_headers(owner, tenant_id),
    )
    assert search.status_code == 200
    assert len(search.json()) == 1

    groups = client.get("/api/v1/groups", headers=_headers(human, tenant_id))
    assert groups.status_code == 200
    chat = next(item for item in groups.json() if item["id"] == group_id)
    assert chat["unread_count"] == 2
    assert chat["last_message"]["content"] == "补充一个线程回复"

    marked = client.post(f"/api/v1/groups/{group_id}/read", headers=_headers(human, tenant_id))
    assert marked.status_code == 204
    groups_after = client.get("/api/v1/groups", headers=_headers(human, tenant_id))
    chat_after = next(item for item in groups_after.json() if item["id"] == group_id)
    assert chat_after["unread_count"] == 0


def test_attachment_upload_and_download(client: TestClient) -> None:
    owner = _register(client, "File Owner")
    tenant_id = _tenant(client, owner)
    group = client.post(
        "/api/v1/groups",
        headers=_headers(owner, tenant_id),
        json={"name": "附件群"},
    ).json()
    group_id = group["id"]

    upload = client.post(
        f"/api/v1/groups/{group_id}/attachments",
        headers=_headers(owner, tenant_id),
        files={"file": ("notes.txt", b"hello orgweave attachment", "text/plain")},
    )
    assert upload.status_code == 201, upload.text
    attachment = upload.json()
    assert attachment["filename"] == "notes.txt"
    assert attachment["size_bytes"] == len(b"hello orgweave attachment")

    message = client.post(
        f"/api/v1/groups/{group_id}/messages",
        headers=_headers(owner, tenant_id),
        json={"content": "附件如下", "attachment_ids": [attachment["id"]]},
    )
    assert message.status_code == 201, message.text
    assert message.json()["attachments"][0]["id"] == attachment["id"]

    download = client.get(
        f"/api/v1/attachments/{attachment['id']}",
        headers=_headers(owner, tenant_id),
    )
    assert download.status_code == 200
    assert download.content == b"hello orgweave attachment"
    assert "attachment" in download.headers["content-disposition"]

    unsupported = client.post(
        f"/api/v1/groups/{group_id}/attachments",
        headers=_headers(owner, tenant_id),
        files={"file": ("evil.exe", b"MZ", "application/x-msdownload")},
    )
    assert unsupported.status_code == 415


def test_websocket_receives_tenant_group_events(client: TestClient) -> None:
    owner = _register(client, "WS Owner")
    tenant_id = _tenant(client, owner)
    group = client.post(
        "/api/v1/groups",
        headers=_headers(owner, tenant_id),
        json={"name": "实时群"},
    ).json()

    with client.websocket_connect(
        f"/ws/v1?token={owner['access_token']}&tenant_id={tenant_id}"
    ) as websocket:
        hello = websocket.receive_json()
        assert hello["type"] == "hello", hello
        assert hello["tenant_id"] == tenant_id
        assert group["id"] in hello["group_ids"]

        settings = OrgWeaveSettings()

        async def publish_allowed() -> None:
            redis = Redis.from_url(settings.redis_url, decode_responses=True)
            try:
                await redis.publish(
                    event_channel(uuid.UUID(tenant_id)),
                    json.dumps(
                        {
                            "type": "message.created",
                            "tenant_id": tenant_id,
                            "group_id": group["id"],
                            "message": {"content": "realtime"},
                            "mentioned_ai_ids": [],
                        }
                    ),
                )
            finally:
                await redis.aclose()

        asyncio.run(publish_allowed())
        event = websocket.receive_json()
        assert event["type"] == "message.created"
        assert event["group_id"] == group["id"]
        assert event["message"]["content"] == "realtime"

        websocket.send_json({"type": "resubscribe"})
        subscriptions = websocket.receive_json()
        assert subscriptions["type"] == "subscriptions"
        assert group["id"] in subscriptions["group_ids"]


def test_websocket_rejects_foreign_tenant(client: TestClient) -> None:
    owner = _register(client, "WS A")
    outsider = _register(client, "WS B")
    tenant_id = _tenant(client, owner)

    with client.websocket_connect(
        f"/ws/v1?token={outsider['access_token']}&tenant_id={tenant_id}"
    ) as websocket:
        error = websocket.receive_json()
        assert error["reason"] == "tenant_forbidden"
