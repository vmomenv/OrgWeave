"""Minimal Phase 0 WebSocket endpoint.

Business events arrive in later phases. This endpoint only proves the /ws/v1
transport works end-to-end (handshake, ping/pong, structured errors) and is
intentionally read-only. Authentication is added together with Phase 1 login;
no tenant or agent data is readable here.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import get_settings

router = APIRouter()

MAX_FRAME_BYTES = 8 * 1024


def _frame(message_type: str, **payload: object) -> str:
    return json.dumps(
        {"type": message_type, "timestamp": datetime.now(UTC).isoformat(), **payload},
        ensure_ascii=False,
    )


@router.websocket("/ws/v1")
async def websocket_endpoint(websocket: WebSocket) -> None:
    settings = get_settings()
    await websocket.accept()
    await websocket.send_text(
        _frame("hello", service="orgweave-api", version=settings.app_version, api="v1")
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
                        phase="0",
                    )
                )
            else:
                await websocket.send_text(_frame("error", reason="unknown_message_type"))
    except WebSocketDisconnect:
        return
