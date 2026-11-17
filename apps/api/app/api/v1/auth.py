"""Authentication endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, set_tenant_context, set_user_context
from app.application.audit import record_audit
from app.application.auth import (
    authenticate_user,
    issue_tokens,
    register_user,
    revoke_refresh_token,
    rotate_refresh_token,
)
from app.application.organization import role_keys_for_member
from app.core.errors import ApiError
from app.models import Member, Tenant, TenantMembership, User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    MeResponse,
    RefreshRequest,
    RegisterRequest,
    TenantSummary,
    TokenPair,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


async def _tenant_summaries(session: AsyncSession, user: User) -> list[TenantSummary]:
    rows = (
        await session.execute(
            select(TenantMembership, Tenant)
            .join(Tenant, Tenant.id == TenantMembership.tenant_id)
            .where(TenantMembership.user_id == user.id)
            .order_by(Tenant.created_at)
        )
    ).all()
    summaries: list[TenantSummary] = []
    for membership, tenant in rows:
        await set_tenant_context(session, tenant.id)
        member = await session.scalar(
            select(Member).where(
                Member.tenant_id == tenant.id,
                Member.user_id == user.id,
                Member.member_type == "human",
            )
        )
        role_keys = await role_keys_for_member(session, tenant.id, member.id) if member else []
        summaries.append(
            TenantSummary(
                id=tenant.id,
                name=tenant.name,
                slug=tenant.slug,
                membership_status=membership.status,
                role_keys=role_keys,
            )
        )
    return summaries


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a user and start a session",
)
async def register(
    body: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthResponse:
    try:
        user = await register_user(
            session,
            email=body.email,
            password=body.password,
            display_name=body.display_name,
        )
    except IntegrityError as exc:
        raise ApiError(409, "email_taken", "该邮箱已注册") from exc

    await set_user_context(session, user.id)
    record_audit(
        session,
        tenant_id=None,
        actor_type="user",
        actor_id=user.id,
        action="auth.registered",
        resource_type="user",
        resource_id=user.id,
    )
    tokens = await issue_tokens(session, user)
    await session.commit()
    return AuthResponse(**tokens, user=UserOut.model_validate(user))


@router.post("/login", response_model=AuthResponse, summary="Login with email and password")
async def login(
    body: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthResponse:
    user = await authenticate_user(session, email=body.email, password=body.password)
    if user is None:
        raise ApiError(401, "invalid_credentials", "邮箱或密码错误")
    if not user.is_active:
        raise ApiError(403, "account_disabled", "账号已被禁用")

    await set_user_context(session, user.id)
    record_audit(
        session,
        tenant_id=None,
        actor_type="user",
        actor_id=user.id,
        action="auth.login",
        resource_type="user",
        resource_id=user.id,
    )
    tokens = await issue_tokens(session, user)
    await session.commit()
    return AuthResponse(**tokens, user=UserOut.model_validate(user))


@router.post("/refresh", response_model=TokenPair, summary="Rotate a refresh token")
async def refresh(
    body: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TokenPair:
    try:
        user, tokens = await rotate_refresh_token(session, body.refresh_token)
    except ApiError:
        await session.rollback()
        raise
    await set_user_context(session, user.id)
    record_audit(
        session,
        tenant_id=None,
        actor_type="user",
        actor_id=user.id,
        action="auth.refreshed",
        resource_type="session",
    )
    await session.commit()
    return TokenPair(**tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke a refresh token")
async def logout(
    body: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    await revoke_refresh_token(session, body.refresh_token)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=MeResponse, summary="Current user and tenants")
async def me(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MeResponse:
    tenants = await _tenant_summaries(session, user)
    await session.commit()
    return MeResponse(user=UserOut.model_validate(user), tenants=tenants)
