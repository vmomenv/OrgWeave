"""Invitation lifecycle."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    TenantContext,
    get_current_user,
    get_session,
    require_permission,
)
from app.application.audit import record_audit
from app.application.auth import normalize_email
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.security import hash_token
from app.models import Invitation, Role, User
from app.schemas.org import (
    AcceptInvitationRequest,
    InvitationCreate,
    InvitationCreated,
    InvitationOut,
)

router = APIRouter(prefix="/invitations", tags=["invitations"])


@router.get(
    "",
    response_model=list[InvitationOut],
    summary="List invitations in the current tenant",
)
async def list_invitations(
    context: Annotated[TenantContext, Depends(require_permission("invitation.manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[InvitationOut]:
    rows = (
        await session.scalars(
            select(Invitation)
            .where(Invitation.tenant_id == context.tenant_id)
            .order_by(Invitation.created_at.desc())
        )
    ).all()
    await session.commit()
    return [InvitationOut.model_validate(row) for row in rows]


@router.post(
    "",
    response_model=InvitationCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Create an invitation token (delivery is manual in Phase 1)",
)
async def create_invitation(
    body: InvitationCreate,
    context: Annotated[TenantContext, Depends(require_permission("invitation.manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InvitationCreated:
    role = await session.scalar(select(Role).where(Role.key == body.role_key))
    if role is None:
        raise ApiError(422, "invalid_role", "邀请角色不存在")
    email = normalize_email(body.email)
    existing_member = await session.scalar(
        select(Invitation.id).where(
            Invitation.tenant_id == context.tenant_id,
            Invitation.email == email,
            Invitation.status == "pending",
        )
    )
    if existing_member is not None:
        raise ApiError(409, "invitation_exists", "该邮箱已有待接受的邀请")

    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(hours=get_settings().invitation_ttl_hours)
    invitation = Invitation(
        tenant_id=context.tenant_id,
        email=email,
        token_hash=hash_token(raw_token),
        role_key=role.key,
        status="pending",
        invited_by=context.user_id,
        expires_at=expires_at,
    )
    session.add(invitation)
    await session.flush()
    record_audit(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_id=context.user_id,
        action="invitation.created",
        resource_type="invitation",
        resource_id=invitation.id,
        metadata={"email": email, "role": role.key},
    )
    await session.commit()
    return InvitationCreated(
        id=invitation.id,
        email=invitation.email,
        role_key=invitation.role_key,
        status=invitation.status,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
        token=raw_token,
    )


@router.delete(
    "/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a pending invitation",
)
async def revoke_invitation(
    invitation_id: uuid.UUID,
    context: Annotated[TenantContext, Depends(require_permission("invitation.manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    invitation = await session.scalar(
        select(Invitation).where(
            Invitation.id == invitation_id, Invitation.tenant_id == context.tenant_id
        )
    )
    if invitation is None:
        raise ApiError(404, "invitation_not_found", "邀请不存在")
    if invitation.status != "pending":
        raise ApiError(409, "invitation_not_pending", "该邀请已处理")
    invitation.status = "revoked"
    record_audit(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_id=context.user_id,
        action="invitation.revoked",
        resource_type="invitation",
        resource_id=invitation.id,
    )
    await session.commit()


@router.post(
    "/accept",
    response_model=dict,
    summary="Accept an invitation as the authenticated user",
)
async def accept_invitation(
    body: AcceptInvitationRequest,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    try:
        tenant_id = await session.scalar(
            text("SELECT orgweave_accept_invitation(:token_hash, :user_id)"),
            {"token_hash": hash_token(body.token), "user_id": str(user.id)},
        )
        await session.commit()
    except DBAPIError as exc:
        await session.rollback()
        message = str(exc.orig)
        mapping = {
            "invitation_not_found": (404, "invitation_not_found", "邀请不存在"),
            "invitation_not_pending": (409, "invitation_not_pending", "该邀请已处理"),
            "invitation_expired": (410, "invitation_expired", "邀请已过期"),
            "invitation_email_mismatch": (
                403,
                "invitation_email_mismatch",
                "邀请邮箱与当前账号不一致",
            ),
        }
        for marker, (status_code, code, detail) in mapping.items():
            if marker in message:
                raise ApiError(status_code, code, detail) from exc
        raise ApiError(400, "invitation_failed", "接受邀请失败") from exc

    # Return the tenant so the client can switch context immediately.
    from app.models import Tenant

    tenant = await session.get(Tenant, tenant_id)
    return {
        "tenant_id": str(tenant_id),
        "tenant_name": tenant.name if tenant else None,
        "status": "accepted",
    }
