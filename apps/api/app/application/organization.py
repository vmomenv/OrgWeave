"""Organization helpers shared by Phase 1 routers."""

from __future__ import annotations

import re
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Member, MemberRole, Role
from app.schemas.org import MemberOut, RoleSummary


def slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if len(base) < 2:
        base = "tenant"
    base = base[:60].strip("-") or "tenant"
    return f"{base}-{secrets.token_hex(3)}"


async def role_keys_for_member(
    session: AsyncSession, tenant_id: uuid.UUID, member_id: uuid.UUID
) -> list[str]:
    rows = (
        (
            await session.execute(
                select(Role.key)
                .join(MemberRole, MemberRole.role_id == Role.id)
                .where(MemberRole.tenant_id == tenant_id, MemberRole.member_id == member_id)
            )
        )
        .scalars()
        .all()
    )
    return sorted(rows)


async def member_roles(
    session: AsyncSession, tenant_id: uuid.UUID, member_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[RoleSummary]]:
    if not member_ids:
        return {}
    rows = (
        await session.execute(
            select(MemberRole.member_id, Role.key, Role.name)
            .join(Role, Role.id == MemberRole.role_id)
            .where(MemberRole.tenant_id == tenant_id, MemberRole.member_id.in_(member_ids))
        )
    ).all()
    result: dict[uuid.UUID, list[RoleSummary]] = {member_id: [] for member_id in member_ids}
    for member_id, key, name in rows:
        result[member_id].append(RoleSummary(key=key, name=name))
    for roles in result.values():
        roles.sort(key=lambda role: role.key)
    return result


async def members_to_out(
    session: AsyncSession, tenant_id: uuid.UUID, members: list[Member]
) -> list[MemberOut]:
    roles = await member_roles(session, tenant_id, [member.id for member in members])
    return [
        MemberOut.model_validate(member).model_copy(update={"roles": roles.get(member.id, [])})
        for member in members
    ]


async def get_member_or_none(
    session: AsyncSession, tenant_id: uuid.UUID, member_id: uuid.UUID
) -> Member | None:
    return await session.scalar(
        select(Member).where(Member.tenant_id == tenant_id, Member.id == member_id)
    )
