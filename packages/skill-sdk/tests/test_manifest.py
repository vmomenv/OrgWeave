from __future__ import annotations

import pytest
from orgweave_skill_sdk import SkillManifest, parse_skill_manifest
from pydantic import ValidationError


def test_valid_manifest() -> None:
    manifest = parse_skill_manifest(
        {
            "name": "pdf-report",
            "version": "1.0.0",
            "description": "Generate a PDF report",
            "entrypoint": "main.py",
            "permissions": ["files.read", "files.write"],
        }
    )

    assert manifest.runtime == "python"
    assert manifest.timeout_seconds == 30
    assert manifest.network_access is False


def test_version_must_be_semver() -> None:
    with pytest.raises(ValidationError, match="semver"):
        SkillManifest(
            name="pdf-report",
            version="v1",
            description="bad",
            entrypoint="main.py",
        )


def test_entrypoint_cannot_escape_package() -> None:
    with pytest.raises(ValidationError, match="inside the skill package"):
        SkillManifest(
            name="pdf-report",
            version="1.0.0",
            description="bad",
            entrypoint="../../etc/passwd",
        )


def test_permissions_must_be_scoped() -> None:
    with pytest.raises(ValidationError, match="scoped"):
        SkillManifest(
            name="pdf-report",
            version="1.0.0",
            description="bad",
            entrypoint="main.py",
            permissions=["root"],
        )
