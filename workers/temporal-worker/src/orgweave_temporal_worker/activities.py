"""Phase 0 activity: returns a deterministic acknowledgement payload."""

from __future__ import annotations

import socket
from datetime import UTC, datetime
from typing import Any

from temporalio import activity


@activity.defn
async def ping_activity(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "pong_at": datetime.now(UTC).isoformat(),
        "worker": socket.gethostname(),
    }
