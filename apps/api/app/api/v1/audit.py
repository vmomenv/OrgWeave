"""Audit log read API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, get_session, require_permission
from app.models import AuditLog
from app.schemas.org import AuditLogOut

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditLogOut], summary="Recent audit events in the tenant")
async def list_audit_logs(
    context: Annotated[TenantContext, Depends(require_permission("audit.read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AuditLogOut]:
    rows = (
        await session.scalars(
            select(AuditLog)
            .where(AuditLog.tenant_id == context.tenant_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    await session.commit()
    return [
        AuditLogOut(
            id=row.id,
            tenant_id=row.tenant_id,
            actor_type=row.actor_type,
            actor_id=row.actor_id,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            result=row.result,
            metadata=row.metadata_,
            created_at=row.created_at,
        )
        for row in rows
    ]
