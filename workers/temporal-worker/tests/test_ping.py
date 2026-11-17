from __future__ import annotations

import pytest
from orgweave_temporal_worker.activities import ping_activity
from orgweave_temporal_worker.workflows import PingWorkflow


@pytest.mark.asyncio
async def test_ping_activity_returns_timestamp() -> None:
    result = await ping_activity("smoke")

    assert result["name"] == "smoke"
    assert "T" in result["pong_at"]
    assert result["worker"]


def test_ping_workflow_is_registered_with_expected_name() -> None:
    assert PingWorkflow.__temporal_workflow_definition.name == "PingWorkflow"
