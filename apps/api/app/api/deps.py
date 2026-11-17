"""Shared API dependencies: database session, authentication, tenant context."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.security import decode_access_token
from app.infrastructure.health.probes import Probe
from app.models import Member, MemberRole, Role, RolePermission, Tenant, TenantMembership, User

_bearer = HTTPBearer(auto_error=False)


def get_health_probes(request: Request) -> list[Probe]:
    return request.app.state.health_probes


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


async def set_user_context(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": str(user_id)}
    )


async def set_tenant_context(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise ApiError(401, "not_authenticated", "请先登录")
    try:
        user_id = decode_access_token(credentials.credentials)
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise ApiError(401, "invalid_token", "登录令牌无效或已过期") from exc

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise ApiError(401, "invalid_token", "登录令牌无效或已过期")
    await set_user_context(session, user.id)
    return user


@dataclass(frozen=True)
class TenantContext:
    tenant: Tenant
    membership: TenantMembership
    member: Member
    role_keys: list[str]
    permissions: set[str]

    @property
    def tenant_id(self) -> uuid.UUID:
        return self.tenant.id

    @property
    def user_id(self) -> uuid.UUID:
        return self.membership.user_id


async def get_tenant_context(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    tenant_header: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
) -> TenantContext:
    if not tenant_header:
        raise ApiError(400, "tenant_required", "请求必须包含 X-Tenant-ID")
    try:
        tenant_id = uuid.UUID(tenant_header)
    except ValueError as exc:
        raise ApiError(400, "invalid_tenant", "X-Tenant-ID 不是合法 UUID") from exc

    membership = await session.scalar(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == user.id,
            TenantMembership.status == "active",
        )
    )
    if membership is None:
        # Do not disclose whether the tenant exists.
        raise ApiError(403, "tenant_forbidden", "无权访问该租户")

    await set_tenant_context(session, tenant_id)

    tenant = await session.get(Tenant, tenant_id)
    member = await session.scalar(
        select(Member).where(
            Member.tenant_id == tenant_id,
            Member.member_type == "human",
            Member.user_id == user.id,
            Member.status == "active",
        )
    )
    if tenant is None or member is None:
        raise ApiError(403, "tenant_forbidden", "无权访问该租户")

    role_rows = (
        (
            await session.execute(
                select(Role.key)
                .join(MemberRole, MemberRole.role_id == Role.id)
                .where(MemberRole.tenant_id == tenant_id, MemberRole.member_id == member.id)
            )
        )
        .scalars()
        .all()
    )
    permission_rows = (
        (
            await session.execute(
                select(RolePermission.permission_key)
                .join(MemberRole, MemberRole.role_id == RolePermission.role_id)
                .where(MemberRole.tenant_id == tenant_id, MemberRole.member_id == member.id)
                .distinct()
            )
        )
        .scalars()
        .all()
    )

    return TenantContext(
        tenant=tenant,
        membership=membership,
        member=member,
        role_keys=sorted(role_rows),
        permissions=set(permission_rows),
    )


def require_permission(permission: str) -> Callable[..., Awaitable[TenantContext]]:
    async def _checker(
        context: Annotated[TenantContext, Depends(get_tenant_context)],
    ) -> TenantContext:
        if permission not in context.permissions:
            raise ApiError(403, "permission_denied", f"缺少权限：{permission}")
        return context

    return _checker


__all__ = [
    "Probe",
    "TenantContext",
    "get_current_user",
    "get_session",
    "get_tenant_context",
    "require_permission",
    "set_tenant_context",
    "set_user_context",
]
