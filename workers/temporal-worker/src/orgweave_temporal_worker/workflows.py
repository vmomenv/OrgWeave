"""Phase 0 workflow used by the end-to-end Temporal smoke test."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from orgweave_temporal_worker.activities import ping_activity


@workflow.defn
class PingWorkflow:
    @workflow.run
    async def run(self, name: str = "phase0") -> dict[str, Any]:
        result = await workflow.execute_activity(
            ping_activity,
            name,
            start_to_close_timeout=timedelta(seconds=10),
        )
        return {
            "workflow": "PingWorkflow",
            "workflow_id": workflow.info().workflow_id,
            "activity": result,
        }
