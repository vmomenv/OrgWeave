"""OrgWeave v1 API router."""

from fastapi import APIRouter

from app.api.v1 import health, meta

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(meta.router)

__all__ = ["api_router"]
