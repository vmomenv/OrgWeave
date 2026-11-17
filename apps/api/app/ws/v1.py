"""Authenticated Phase 1 WebSocket transport.

Only authenticated users may connect. No tenant data is exposed; message
subscriptions arrive in Phase 2 and must re-check tenant membership.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.deps import set_user_context
from app.core.config import get_settings
from app.core.security import decode_access_token
from app.models import User

router = APIRouter()

MAX_FRAME_BYTES = 8 * 1024


def _frame(message_type: str, **payload: object) -> str:
    return json.dumps(
        {"type": message_type, "timestamp": datetime.now(UTC).isoformat(), **payload},
        ensure_ascii=False,
    )


async def _reject(websocket: WebSocket, reason: str) -> None:
    await websocket.accept()
    await websocket.send_text(_frame("error", reason=reason))
    await websocket.close(code=4401)


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

    factory = websocket.app.state.session_factory
    async with factory() as session:  # type: AsyncSession
        user = await session.get(User, user_id)
        if user is None or not user.is_active:
            await _reject(websocket, "unauthorized")
            return
        await set_user_context(session, user.id)
        display_name = user.display_name

    await websocket.accept()
    await websocket.send_text(
        _frame(
            "hello",
            service="orgweave-api",
            version=settings.app_version,
            api="v1",
            user_id=str(user_id),
            display_name=display_name,
        )
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
                        phase="1",
                    )
                )
            else:
                await websocket.send_text(_frame("error", reason="unknown_message_type"))
    except WebSocketDisconnect:
        return
