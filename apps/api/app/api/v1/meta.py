"""Service metadata endpoint used by clients and smoke tests."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.health import MetaResponse

router = APIRouter(tags=["meta"])


@router.get("/meta", response_model=MetaResponse, summary="Service metadata")
async def meta() -> MetaResponse:
    settings = get_settings()
    return MetaResponse(version=settings.app_version)
