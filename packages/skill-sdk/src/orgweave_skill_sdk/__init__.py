"""Skill manifest contract.

Phase 0 only validates manifests. Installation, versioning and the isolated
Skill Runner execution path arrive in Phase 5.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


class SkillManifest(BaseModel):
    name: str
    version: str
    description: str = Field(min_length=1, max_length=500)
    runtime: Literal["python", "node", "http"] = "python"
    entrypoint: str = Field(min_length=1)
    permissions: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(default=30, ge=1, le=600)
    network_access: bool = False

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if not _NAME_RE.fullmatch(value):
            raise ValueError("skill name must be lowercase kebab-case, 3-64 characters")
        return value

    @field_validator("version")
    @classmethod
    def _validate_version(cls, value: str) -> str:
        if not _SEMVER_RE.fullmatch(value):
            raise ValueError("skill version must be immutable semver, e.g. 1.0.0")
        return value

    @field_validator("entrypoint")
    @classmethod
    def _entrypoint_is_relative(cls, value: str) -> str:
        if value.startswith("/") or ".." in value.split("/"):
            raise ValueError("entrypoint must stay inside the skill package")
        return value

    @field_validator("permissions")
    @classmethod
    def _permissions_are_scoped(cls, values: list[str]) -> list[str]:
        for permission in values:
            if "." not in permission:
                raise ValueError("permissions must be scoped, e.g. 'files.read'")
        return values


def parse_skill_manifest(data: dict[str, Any]) -> SkillManifest:
    return SkillManifest.model_validate(data)
