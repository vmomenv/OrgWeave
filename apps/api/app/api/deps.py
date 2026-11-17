"""Shared API dependencies."""

from __future__ import annotations

from fastapi import Request

from app.infrastructure.health.probes import Probe


def get_health_probes(request: Request) -> list[Probe]:
    return request.app.state.health_probes


__all__ = ["Probe", "get_health_probes"]
