"""API configuration facade.

The authoritative settings live in ``orgweave_shared.settings`` so the API and
every worker read the same environment contract.
"""

from __future__ import annotations

from functools import lru_cache

from orgweave_shared.settings import OrgWeaveSettings


@lru_cache
def get_settings() -> OrgWeaveSettings:
    return OrgWeaveSettings()


__all__ = ["OrgWeaveSettings", "get_settings"]
