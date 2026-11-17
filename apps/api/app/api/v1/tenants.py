"""Tenant listing and creation."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, set_tenant_context
from app.application.organization import role_keys_for_member, slugify
from app.core.errors import ApiError
from app.models import Member, Tenant, TenantMembership, User
from app.schemas.auth import TenantSummary
from app.schemas.org import TenantCreate, TenantOut

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.get("", response_model=list[TenantSummary], summary="Tenants for the current user")
async def list_tenants(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[TenantSummary]:
    rows = (
        await session.execute(
            select(TenantMembership, Tenant)
            .join(Tenant, Tenant.id == TenantMembership.tenant_id)
            .where(TenantMembership.user_id == user.id)
            .order_by(Tenant.created_at)
        )
    ).all()
    result: list[TenantSummary] = []
    for membership, tenant in rows:
        await set_tenant_context(session, tenant.id)
        member = await session.scalar(
            select(Member).where(
                Member.tenant_id == tenant.id,
                Member.user_id == user.id,
                Member.member_type == "human",
            )
        )
        result.append(
            TenantSummary(
                id=tenant.id,
                name=tenant.name,
                slug=tenant.slug,
                membership_status=membership.status,
                role_keys=(
                    await role_keys_for_member(session, tenant.id, member.id) if member else []
                ),
            )
        )
    await session.commit()
    return result


@router.post(
    "",
    response_model=TenantOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a tenant with the caller as owner",
)
async def create_tenant(
    body: TenantCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TenantOut:
    slug = body.slug or slugify(body.name)
    try:
        tenant_id = await session.scalar(
            text("SELECT orgweave_create_tenant(:user_id, :name, :slug, :display_name)"),
            {
                "user_id": str(user.id),
                "name": body.name.strip(),
                "slug": slug,
                "display_name": user.display_name,
            },
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiError(409, "tenant_slug_taken", "租户标识已存在，请更换名称或 slug") from exc

    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise ApiError(500, "tenant_creation_failed", "租户创建失败")
    await set_tenant_context(session, tenant.id)
    await session.commit()
    return TenantOut.model_validate(tenant)


@router.get("/{tenant_id}", response_model=TenantOut, summary="Get a tenant the user belongs to")
async def get_tenant(
    tenant_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TenantOut:
    membership = await session.scalar(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == user.id,
        )
    )
    if membership is None:
        raise ApiError(404, "tenant_not_found", "租户不存在")
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise ApiError(404, "tenant_not_found", "租户不存在")
    await session.commit()
    return TenantOut.model_validate(tenant)
