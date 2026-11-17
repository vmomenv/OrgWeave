"""Execute the Phase 0 Temporal ping workflow and verify the result."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import timedelta
from uuid import uuid4

from orgweave_shared.settings import OrgWeaveSettings
from orgweave_temporal_worker.workflows import PingWorkflow
from temporalio.client import Client


async def main() -> int:
    settings = OrgWeaveSettings()
    client = await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)
    handle = await client.start_workflow(
        PingWorkflow.run,
        "phase0-smoke",
        id=f"phase0-ping-{uuid4()}",
        task_queue=settings.temporal_task_queue,
        execution_timeout=timedelta(seconds=30),
    )
    result = await asyncio.wait_for(handle.result(), timeout=30)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    activity = result.get("activity", {})
    if result.get("workflow") != "PingWorkflow" or activity.get("name") != "phase0-smoke":
        print("SMOKE FAILED: unexpected workflow result", file=sys.stderr)
        return 1
    print("TEMPORAL SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
