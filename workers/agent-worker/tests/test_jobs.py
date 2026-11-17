from __future__ import annotations

import pytest
from orgweave_agent_sdk import AgentJob
from orgweave_agent_worker.jobs import UnsupportedJobType, process_job


def test_ping_job_returns_echo() -> None:
    job = AgentJob(type="system.ping", payload={"hello": "orgweave"})

    result = process_job(job)

    assert result["pong"] is True
    assert result["echo"] == {"hello": "orgweave"}
    assert result["job_type"] == "system.ping"


def test_unsupported_job_type_raises() -> None:
    job = AgentJob(type="system.unsupported")

    with pytest.raises(UnsupportedJobType, match="system.unsupported"):
        process_job(job)
