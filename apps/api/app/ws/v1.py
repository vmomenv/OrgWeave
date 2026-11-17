"""Authenticated WebSocket transport with Phase 2 tenant event subscription."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import set_tenant_context, set_user_context
from app.application.chat import event_channel
from app.core.config import get_settings
from app.core.security import decode_access_token
from app.models import GroupMember, Member, TenantMembership, User

logger = logging.getLogger("orgweave.ws")
router = APIRouter()

MAX_FRAME_BYTES = 8 * 1024


def _frame(message_type: str, **payload: object) -> str:
    return json.dumps(
        {"type": message_type, "timestamp": datetime.now(UTC).isoformat(), **payload},
        ensure_ascii=False,
    )


async def _reject(websocket: WebSocket, reason: str, code: int = 4401) -> None:
    await websocket.accept()
    await websocket.send_text(_frame("error", reason=reason))
    await websocket.close(code=code)


async def _load_group_ids(
    session: AsyncSession, tenant_id: uuid.UUID, member_id: uuid.UUID
) -> set[str]:
    rows = (
        await session.scalars(
            select(GroupMember.group_id).where(
                GroupMember.tenant_id == tenant_id, GroupMember.member_id == member_id
            )
        )
    ).all()
    return {str(group_id) for group_id in rows}


async def _listen_tenant_events(
    websocket: WebSocket,
    pubsub,
    allowed_groups: set[str],
    send_lock: asyncio.Lock,
) -> None:
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is None:
                await asyncio.sleep(0.05)
                continue
            try:
                event = json.loads(message["data"])
            except (TypeError, json.JSONDecodeError):
                continue
            if str(event.get("group_id")) not in allowed_groups:
                continue
            async with send_lock:
                await websocket.send_text(json.dumps(event, ensure_ascii=False))
    except asyncio.CancelledError:
        raise
    except Exception:
        return


@router.websocket("/ws/v1")
async def websocket_endpoint(websocket: WebSocket) -> None:
    settings = get_settings()
    token = websocket.query_params.get("token")
    if not token:
        await _reject(websocket, "unauthorized")
        return

    try:
        user_id = decode_access_token(token)
    except (jwt.InvalidTokenError, ValueError):
        await _reject(websocket, "unauthorized")
        return

    tenant_id_raw = websocket.query_params.get("tenant_id")
    tenant_id: uuid.UUID | None = None
    if tenant_id_raw:
        try:
            tenant_id = uuid.UUID(tenant_id_raw)
        except ValueError:
            await _reject(websocket, "invalid_tenant", 4400)
            return

    factory = websocket.app.state.session_factory
    group_ids: set[str] = set()
    async with factory() as session:  # type: AsyncSession
        user = await session.get(User, user_id)
        if user is None or not user.is_active:
            await _reject(websocket, "unauthorized")
            return
        await set_user_context(session, user.id)
        display_name = user.display_name

        if tenant_id is not None:
            membership = await session.scalar(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == tenant_id,
                    TenantMembership.user_id == user.id,
                    TenantMembership.status == "active",
                )
            )
            if membership is None:
                await _reject(websocket, "tenant_forbidden", 4403)
                return
            await set_tenant_context(session, tenant_id)
            member = await session.scalar(
                select(Member).where(
                    Member.tenant_id == tenant_id,
                    Member.user_id == user.id,
                    Member.member_type == "human",
                    Member.status == "active",
                )
            )
            if member is None:
                await _reject(websocket, "tenant_forbidden", 4403)
                return
            group_ids = await _load_group_ids(session, tenant_id, member.id)
            member_id = member.id

    await websocket.accept()
    await websocket.send_text(
        _frame(
            "hello",
            service="orgweave-api",
            version=settings.app_version,
            api="v2",
            user_id=str(user_id),
            display_name=display_name,
            tenant_id=str(tenant_id) if tenant_id else None,
            group_ids=sorted(group_ids),
        )
    )

    send_lock = asyncio.Lock()
    pubsub = None
    listener_task: asyncio.Task | None = None
    if tenant_id is not None:
        pubsub = websocket.app.state.redis.pubsub()
        await pubsub.subscribe(event_channel(tenant_id))
        listener_task = asyncio.create_task(
            _listen_tenant_events(websocket, pubsub, group_ids, send_lock)
        )

    try:
        while True:
            raw = await websocket.receive_text()
            if len(raw.encode("utf-8")) > MAX_FRAME_BYTES:
                await websocket.send_text(_frame("error", reason="frame_too_large"))
                await websocket.close(code=1009)
                return
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(_frame("error", reason="invalid_json"))
                continue
            if not isinstance(message, dict):
                await websocket.send_text(_frame("error", reason="invalid_message"))
                continue
            message_type = message.get("type")
            if message_type == "ping":
                await websocket.send_text(_frame("pong"))
            elif message_type == "server.info":
                await websocket.send_text(
                    _frame(
                        "server.info",
                        service="orgweave-api",
                        version=settings.app_version,
                        phase="2",
                    )
                )
            elif message_type == "resubscribe" and tenant_id is not None:
                async with factory() as session:  # type: AsyncSession
                    await set_user_context(session, user_id)
                    await set_tenant_context(session, tenant_id)
                    group_ids = await _load_group_ids(session, tenant_id, member_id)
                if listener_task is not None:
                    listener_task.cancel()
                    try:
                        await listener_task
                    except asyncio.CancelledError:
                        pass
                if pubsub is not None:
                    await pubsub.unsubscribe(event_channel(tenant_id))
                    await pubsub.aclose()
                pubsub = websocket.app.state.redis.pubsub()
                await pubsub.subscribe(event_channel(tenant_id))
                listener_task = asyncio.create_task(
                    _listen_tenant_events(websocket, pubsub, group_ids, send_lock)
                )
                await websocket.send_text(_frame("subscriptions", group_ids=sorted(group_ids)))
            else:
                await websocket.send_text(_frame("error", reason="unknown_message_type"))
    except WebSocketDisconnect:
        return
    finally:
        if listener_task is not None:
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass
        if pubsub is not None:
            try:
                await pubsub.unsubscribe(event_channel(tenant_id))
                await pubsub.aclose()
            except Exception:
                pass
