"""Member management and role assignment."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    TenantContext,
    get_session,
    require_permission,
    set_tenant_context,
)
from app.application.agent_service import ensure_agent_for_member
from app.application.audit import record_audit
from app.application.organization import get_member_or_none, members_to_out, role_keys_for_member
from app.core.errors import ApiError
from app.models import Member, MemberRole, Role, TenantMembership, User
from app.schemas.org import (
    MemberCreate,
    MemberOut,
    MemberRolesUpdate,
    MemberUpdate,
    PermissionOut,
    RoleOut,
)

router = APIRouter(tags=["members"])


async def _roles_by_keys(session: AsyncSession, keys: list[str]) -> list[Role]:
    unique = sorted(set(keys))
    roles = (await session.scalars(select(Role).where(Role.key.in_(unique)))).all()
    if len(roles) != len(unique):
        missing = unique.copy()
        for role in roles:
            missing.remove(role.key)
        raise ApiError(
            422,
            "invalid_roles",
            "存在无效角色",
            details={"missing": missing},
        )
    return list(roles)


async def _validate_department_and_manager(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    department_id: uuid.UUID | None,
    manager_id: uuid.UUID | None,
    member_id: uuid.UUID | None = None,
) -> None:
    if department_id is not None:
        exists = await session.scalar(
            text("SELECT 1 FROM departments WHERE tenant_id = :t AND id = :d"),
            {"t": str(tenant_id), "d": str(department_id)},
        )
        if not exists:
            raise ApiError(422, "invalid_department", "部门不存在")
    if manager_id is not None:
        if member_id is not None and manager_id == member_id:
            raise ApiError(422, "invalid_manager", "成员不能成为自己的上级")
        manager = await get_member_or_none(session, tenant_id, manager_id)
        if manager is None:
            raise ApiError(422, "invalid_manager", "上级成员不存在")
        if member_id is not None:
            cycle = await session.scalar(
                text(
                    """
                    WITH RECURSIVE chain AS (
                        SELECT id, manager_id FROM members
                        WHERE tenant_id = :tenant_id AND id = :manager
                        UNION ALL
                        SELECT m.id, m.manager_id
                        FROM members m
                        JOIN chain c ON m.id = c.manager_id
                        WHERE m.tenant_id = :tenant_id
                    )
                    SELECT EXISTS (SELECT 1 FROM chain WHERE id = :member)
                    """
                ),
                {
                    "tenant_id": str(tenant_id),
                    "manager": str(manager_id),
                    "member": str(member_id),
                },
            )
            if cycle:
                raise ApiError(422, "manager_cycle", "上下级关系不能形成环")


async def _load_member(session: AsyncSession, tenant_id: uuid.UUID, member_id: uuid.UUID) -> Member:
    member = await get_member_or_none(session, tenant_id, member_id)
    if member is None:
        raise ApiError(404, "member_not_found", "成员不存在")
    return member


@router.get(
    "/members",
    response_model=list[MemberOut],
    summary="List members in the current tenant",
)
async def list_members(
    context: Annotated[TenantContext, Depends(require_permission("member.read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    member_type: Annotated[Literal["human", "ai"] | None, Query()] = None,
    department_id: Annotated[uuid.UUID | None, Query()] = None,
    query: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[MemberOut]:
    statement = select(Member).where(Member.tenant_id == context.tenant_id)
    if member_type is not None:
        statement = statement.where(Member.member_type == member_type)
    if department_id is not None:
        statement = statement.where(Member.department_id == department_id)
    if query:
        pattern = f"%{query.strip()}%"
        statement = statement.where(
            or_(Member.display_name.ilike(pattern), Member.title.ilike(pattern))
        )
    members = list(
        (await session.scalars(statement.order_by(Member.created_at).limit(limit))).all()
    )
    result = await members_to_out(session, context.tenant_id, members)
    await session.commit()
    return result


@router.get("/members/{member_id}", response_model=MemberOut, summary="Get a member")
async def get_member(
    member_id: uuid.UUID,
    context: Annotated[TenantContext, Depends(require_permission("member.read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MemberOut:
    member = await _load_member(session, context.tenant_id, member_id)
    result = (await members_to_out(session, context.tenant_id, [member]))[0]
    await session.commit()
    return result


@router.post(
    "/members",
    response_model=MemberOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a human or AI member",
)
async def create_member(
    body: MemberCreate,
    context: Annotated[TenantContext, Depends(require_permission("member.manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MemberOut:
    roles = await _roles_by_keys(session, body.role_keys)
    await _validate_department_and_manager(
        session,
        context.tenant_id,
        department_id=body.department_id,
        manager_id=body.manager_id,
    )

    if body.member_type == "human":
        user = await session.get(User, body.user_id) if body.user_id else None
        if user is None or not user.is_active:
            raise ApiError(422, "invalid_user", "关联用户不存在或已禁用")
        existing = await session.scalar(
            select(Member.id).where(
                Member.tenant_id == context.tenant_id, Member.user_id == user.id
            )
        )
        if existing is not None:
            raise ApiError(409, "member_exists", "该用户已是本租户成员")
        membership = await session.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == context.tenant_id,
                TenantMembership.user_id == user.id,
            )
        )
        if membership is None:
            session.add(
                TenantMembership(tenant_id=context.tenant_id, user_id=user.id, status="active")
            )

    member = Member(
        tenant_id=context.tenant_id,
        member_type=body.member_type,
        user_id=body.user_id,
        display_name=body.display_name.strip(),
        title=body.title,
        bio=body.bio,
        avatar_url=body.avatar_url,
        department_id=body.department_id,
        manager_id=body.manager_id,
        status="active",
        ai_enabled=body.ai_enabled if body.member_type == "ai" else False,
    )
    session.add(member)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiError(409, "member_conflict", "成员创建冲突，请检查用户或部门") from exc

    for role in roles:
        session.add(MemberRole(tenant_id=context.tenant_id, member_id=member.id, role_id=role.id))

    if member.member_type == "ai":
        await ensure_agent_for_member(session, context.tenant_id, member)

    record_audit(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_id=context.user_id,
        action="member.created",
        resource_type="member",
        resource_id=member.id,
        metadata={"member_type": member.member_type, "display_name": member.display_name},
    )
    await session.commit()
    await set_tenant_context(session, context.tenant_id)
    return (await members_to_out(session, context.tenant_id, [member]))[0]


@router.patch("/members/{member_id}", response_model=MemberOut, summary="Update a member")
async def update_member(
    member_id: uuid.UUID,
    body: MemberUpdate,
    context: Annotated[TenantContext, Depends(require_permission("member.manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MemberOut:
    member = await _load_member(session, context.tenant_id, member_id)
    fields = body.model_fields_set

    await _validate_department_and_manager(
        session,
        context.tenant_id,
        department_id=body.department_id if "department_id" in fields else None,
        manager_id=body.manager_id if "manager_id" in fields else None,
        member_id=member.id,
    )

    if "display_name" in fields and body.display_name is not None:
        member.display_name = body.display_name.strip()
    if "title" in fields:
        member.title = body.title
    if "bio" in fields:
        member.bio = body.bio
    if "avatar_url" in fields:
        member.avatar_url = body.avatar_url
    if "department_id" in fields:
        member.department_id = body.department_id
    if "manager_id" in fields:
        member.manager_id = body.manager_id
    if "status" in fields and body.status is not None:
        member.status = body.status
    if "ai_enabled" in fields and body.ai_enabled is not None:
        member.ai_enabled = body.ai_enabled

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiError(409, "member_conflict", "成员更新冲突") from exc

    record_audit(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_id=context.user_id,
        action="member.updated",
        resource_type="member",
        resource_id=member.id,
        metadata={"fields": sorted(fields)},
    )
    await session.commit()
    await set_tenant_context(session, context.tenant_id)
    return (await members_to_out(session, context.tenant_id, [member]))[0]


@router.put(
    "/members/{member_id}/roles",
    response_model=MemberOut,
    summary="Replace a member's role assignments",
)
async def set_member_roles(
    member_id: uuid.UUID,
    body: MemberRolesUpdate,
    context: Annotated[TenantContext, Depends(require_permission("role.manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MemberOut:
    member = await _load_member(session, context.tenant_id, member_id)
    roles = await _roles_by_keys(session, body.role_keys)
    current_keys = set(await role_keys_for_member(session, context.tenant_id, member.id))
    new_keys = {role.key for role in roles}

    if "owner" in current_keys and "owner" not in new_keys:
        owners = await session.scalar(
            text(
                """
                SELECT count(*) FROM member_roles mr
                JOIN roles r ON r.id = mr.role_id
                WHERE mr.tenant_id = :tenant_id AND r.key = 'owner' AND mr.member_id <> :member
                """
            ),
            {"tenant_id": str(context.tenant_id), "member": str(member.id)},
        )
        if not owners:
            raise ApiError(409, "last_owner", "租户必须至少保留一名 Owner")

    existing_roles = (
        await session.scalars(
            select(MemberRole).where(
                MemberRole.tenant_id == context.tenant_id,
                MemberRole.member_id == member.id,
            )
        )
    ).all()
    for role in existing_roles:
        await session.delete(role)
    for role in roles:
        session.add(MemberRole(tenant_id=context.tenant_id, member_id=member.id, role_id=role.id))

    record_audit(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_id=context.user_id,
        action="member.roles_updated",
        resource_type="member",
        resource_id=member.id,
        metadata={"roles": sorted(new_keys)},
    )
    await session.commit()
    await set_tenant_context(session, context.tenant_id)
    return (await members_to_out(session, context.tenant_id, [member]))[0]


@router.get("/roles", response_model=list[RoleOut], summary="List roles and permissions")
async def list_roles(
    context: Annotated[TenantContext, Depends(require_permission("role.read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[RoleOut]:
    roles = list((await session.scalars(select(Role).order_by(Role.key))).all())
    from app.models import RolePermission

    rows = (
        await session.execute(
            select(RolePermission.role_id, RolePermission.permission_key).order_by(
                RolePermission.permission_key
            )
        )
    ).all()
    mapping: dict[uuid.UUID, list[str]] = {role.id: [] for role in roles}
    for role_id, permission_key in rows:
        mapping.setdefault(role_id, []).append(permission_key)
    result = [
        RoleOut(
            key=role.key,
            name=role.name,
            description=role.description,
            is_system=role.is_system,
            permissions=mapping.get(role.id, []),
        )
        for role in roles
    ]
    await session.commit()
    return result


@router.get(
    "/permissions",
    response_model=list[PermissionOut],
    summary="List permission dictionary",
)
async def list_permissions(
    context: Annotated[TenantContext, Depends(require_permission("role.read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[PermissionOut]:
    from app.models import Permission

    rows = (await session.scalars(select(Permission).order_by(Permission.key))).all()
    await session.commit()
    return [PermissionOut.model_validate(row) for row in rows]
