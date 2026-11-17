from __future__ import annotations

import pytest
from orgweave_agent_sdk import AgentJob, AgentToolSpec, JobResult
from pydantic import ValidationError


def test_job_defaults_are_stable() -> None:
    job = AgentJob(type="system.ping")

    assert job.job_id.int != 0
    assert job.payload == {}
    assert job.attempts == 0
    assert job.created_at.tzinfo is not None


def test_job_type_must_be_namespaced() -> None:
    with pytest.raises(ValidationError, match="namespaced"):
        AgentJob(type="ping")


def test_job_roundtrip_json() -> None:
    job = AgentJob(type="system.ping", payload={"echo": "hello"})
    restored = AgentJob.model_validate_json(job.model_dump_json())

    assert restored == job


def test_job_result_requires_worker() -> None:
    job = AgentJob(type="system.ping")
    result = JobResult(job_id=job.job_id, status="ok", worker="agent-worker")

    assert result.status == "ok"
    assert result.worker == "agent-worker"


def test_tool_name_is_snake_case() -> None:
    with pytest.raises(ValidationError):
        AgentToolSpec(name="Run Shell", description="bad name")

    tool = AgentToolSpec(name="delegate_task", description="Delegate work")
    assert tool.requires_approval is False
