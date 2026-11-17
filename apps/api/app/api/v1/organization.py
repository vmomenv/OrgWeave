"""Current tenant and departments."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    TenantContext,
    get_session,
    get_tenant_context,
    require_permission,
)
from app.application.audit import record_audit
from app.core.errors import ApiError
from app.models import Department, Member
from app.schemas.org import (
    CurrentTenantOut,
    DepartmentCreate,
    DepartmentOut,
    DepartmentUpdate,
    TenantUpdate,
)

router = APIRouter(tags=["organization"])


@router.get("/tenant", response_model=CurrentTenantOut, summary="Current tenant context")
async def current_tenant(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
) -> CurrentTenantOut:
    return CurrentTenantOut(
        id=context.tenant.id,
        name=context.tenant.name,
        slug=context.tenant.slug,
        created_at=context.tenant.created_at,
        membership_status=context.membership.status,
        member_id=context.member.id,
        member_display_name=context.member.display_name,
        role_keys=context.role_keys,
        permissions=sorted(context.permissions),
    )


@router.patch("/tenant", response_model=CurrentTenantOut, summary="Rename the current tenant")
async def update_tenant(
    body: TenantUpdate,
    context: Annotated[TenantContext, Depends(require_permission("tenant.manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CurrentTenantOut:
    name = body.name.strip()
    context.tenant.name = name
    record_audit(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_id=context.user_id,
        action="tenant.updated",
        resource_type="tenant",
        resource_id=context.tenant_id,
        metadata={"name": name},
    )
    await session.commit()
    return CurrentTenantOut(
        id=context.tenant.id,
        name=context.tenant.name,
        slug=context.tenant.slug,
        created_at=context.tenant.created_at,
        membership_status=context.membership.status,
        member_id=context.member.id,
        member_display_name=context.member.display_name,
        role_keys=context.role_keys,
        permissions=sorted(context.permissions),
    )


@router.get(
    "/departments",
    response_model=list[DepartmentOut],
    summary="List departments in the current tenant",
)
async def list_departments(
    context: Annotated[TenantContext, Depends(require_permission("member.read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[DepartmentOut]:
    rows = (
        await session.scalars(
            select(Department)
            .where(Department.tenant_id == context.tenant_id)
            .order_by(Department.name)
        )
    ).all()
    return [DepartmentOut.model_validate(row) for row in rows]


async def _get_department(
    session: AsyncSession, tenant_id: uuid.UUID, department_id: uuid.UUID
) -> Department:
    department = await session.scalar(
        select(Department).where(Department.tenant_id == tenant_id, Department.id == department_id)
    )
    if department is None:
        raise ApiError(404, "department_not_found", "部门不存在")
    return department


async def _would_cycle(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    department_id: uuid.UUID,
    candidate_parent_id: uuid.UUID,
) -> bool:
    result = await session.scalar(
        text(
            """
            WITH RECURSIVE chain AS (
                SELECT id, parent_id
                FROM departments
                WHERE tenant_id = :tenant_id AND id = :candidate
                UNION ALL
                SELECT d.id, d.parent_id
                FROM departments d
                JOIN chain c ON d.id = c.parent_id
                WHERE d.tenant_id = :tenant_id
            )
            SELECT EXISTS (SELECT 1 FROM chain WHERE id = :target)
            """
        ),
        {
            "tenant_id": str(tenant_id),
            "candidate": str(candidate_parent_id),
            "target": str(department_id),
        },
    )
    return bool(result)


@router.post(
    "/departments",
    response_model=DepartmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a department",
)
async def create_department(
    body: DepartmentCreate,
    context: Annotated[TenantContext, Depends(require_permission("department.manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DepartmentOut:
    if body.parent_id is not None:
        await _get_department(session, context.tenant_id, body.parent_id)

    department = Department(
        tenant_id=context.tenant_id,
        name=body.name.strip(),
        parent_id=body.parent_id,
    )
    session.add(department)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiError(409, "department_name_taken", "同级部门名称已存在") from exc

    record_audit(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_id=context.user_id,
        action="department.created",
        resource_type="department",
        resource_id=department.id,
        metadata={
            "name": department.name,
            "parent_id": str(body.parent_id) if body.parent_id else None,
        },
    )
    await session.commit()
    return DepartmentOut.model_validate(department)


@router.patch(
    "/departments/{department_id}",
    response_model=DepartmentOut,
    summary="Update a department",
)
async def update_department(
    department_id: uuid.UUID,
    body: DepartmentUpdate,
    context: Annotated[TenantContext, Depends(require_permission("department.manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DepartmentOut:
    department = await _get_department(session, context.tenant_id, department_id)
    fields = body.model_fields_set

    if "name" in fields and body.name is not None:
        department.name = body.name.strip()
    if "parent_id" in fields:
        if body.parent_id == department.id:
            raise ApiError(422, "department_cycle", "部门不能作为自己的上级")
        if body.parent_id is not None:
            await _get_department(session, context.tenant_id, body.parent_id)
            if await _would_cycle(session, context.tenant_id, department.id, body.parent_id):
                raise ApiError(422, "department_cycle", "上级部门不能是当前部门的下级")
        department.parent_id = body.parent_id

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiError(409, "department_name_taken", "同级部门名称已存在") from exc

    record_audit(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_id=context.user_id,
        action="department.updated",
        resource_type="department",
        resource_id=department.id,
        metadata={"fields": sorted(fields)},
    )
    await session.commit()
    return DepartmentOut.model_validate(department)


@router.delete(
    "/departments/{department_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an empty department",
)
async def delete_department(
    department_id: uuid.UUID,
    context: Annotated[TenantContext, Depends(require_permission("department.manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    department = await _get_department(session, context.tenant_id, department_id)
    children = await session.scalar(
        select(func.count())
        .select_from(Department)
        .where(
            Department.tenant_id == context.tenant_id,
            Department.parent_id == department_id,
        )
    )
    if children:
        raise ApiError(409, "department_not_empty", "请先移动或删除下级部门")
    members = await session.scalar(
        select(func.count())
        .select_from(Member)
        .where(
            Member.tenant_id == context.tenant_id,
            Member.department_id == department_id,
        )
    )
    if members:
        raise ApiError(409, "department_has_members", "请先移出部门内成员")

    await session.delete(department)
    record_audit(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_id=context.user_id,
        action="department.deleted",
        resource_type="department",
        resource_id=department_id,
    )
    await session.commit()
