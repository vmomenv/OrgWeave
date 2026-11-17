"""OrgWeave v1 API router."""

from fastapi import APIRouter

from app.api.v1 import (
    audit,
    auth,
    health,
    invitations,
    members,
    meta,
    organization,
    tenants,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(meta.router)
api_router.include_router(auth.router)
api_router.include_router(tenants.router)
api_router.include_router(organization.router)
api_router.include_router(members.router)
api_router.include_router(invitations.router)
api_router.include_router(audit.router)

__all__ = ["api_router"]
