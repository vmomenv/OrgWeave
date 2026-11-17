"""Chat application services."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.models import (
    Attachment,
    Group,
    GroupMember,
    Member,
    Message,
    MessageMention,
)
from app.schemas.chat import (
    AttachmentOut,
    GroupMemberOut,
    GroupOut,
    MemberRef,
    MessageOut,
)


async def require_membership(
    session: AsyncSession, tenant_id: uuid.UUID, group_id: uuid.UUID, member_id: uuid.UUID
) -> tuple[Group, GroupMember]:
    row = (
        await session.execute(
            select(Group, GroupMember)
            .join(
                GroupMember,
                (GroupMember.group_id == Group.id) & (GroupMember.tenant_id == Group.tenant_id),
            )
            .where(
                Group.tenant_id == tenant_id,
                Group.id == group_id,
                GroupMember.member_id == member_id,
            )
        )
    ).first()
    if row is None:
        raise ApiError(404, "group_not_found", "群聊不存在或无权访问")
    return row[0], row[1]


async def _group_members(
    session: AsyncSession, tenant_id: uuid.UUID, group_id: uuid.UUID
) -> list[GroupMemberOut]:
    rows = (
        await session.execute(
            select(GroupMember, Member)
            .join(
                Member,
                (Member.id == GroupMember.member_id) & (Member.tenant_id == GroupMember.tenant_id),
            )
            .where(GroupMember.tenant_id == tenant_id, GroupMember.group_id == group_id)
            .order_by(GroupMember.joined_at)
        )
    ).all()
    return [
        GroupMemberOut(
            member_id=member.id,
            display_name=member.display_name,
            member_type=member.member_type,
            title=member.title,
            role=membership.role,
            joined_at=membership.joined_at,
            last_read_at=membership.last_read_at,
        )
        for membership, member in rows
    ]


async def _serialize_messages(
    session: AsyncSession, tenant_id: uuid.UUID, messages: list[Message]
) -> list[MessageOut]:
    if not messages:
        return []
    message_ids = [message.id for message in messages]
    sender_ids = {message.sender_member_id for message in messages}

    senders = {
        member.id: member
        for member in (
            await session.scalars(
                select(Member).where(Member.tenant_id == tenant_id, Member.id.in_(sender_ids))
            )
        ).all()
    }
    mention_rows = (
        await session.execute(
            select(MessageMention.message_id, Member)
            .join(
                Member,
                (Member.id == MessageMention.member_id)
                & (Member.tenant_id == MessageMention.tenant_id),
            )
            .where(
                MessageMention.tenant_id == tenant_id,
                MessageMention.message_id.in_(message_ids),
            )
        )
    ).all()
    attachments = (
        await session.scalars(
            select(Attachment).where(
                Attachment.tenant_id == tenant_id,
                Attachment.message_id.in_(message_ids),
            )
        )
    ).all()

    mentions: dict[uuid.UUID, list[MemberRef]] = {mid: [] for mid in message_ids}
    for message_id, member in mention_rows:
        mentions.setdefault(message_id, []).append(
            MemberRef(
                id=member.id, display_name=member.display_name, member_type=member.member_type
            )
        )
    attachment_map: dict[uuid.UUID, list[AttachmentOut]] = {mid: [] for mid in message_ids}
    for attachment in attachments:
        if attachment.message_id is None:
            continue
        attachment_map.setdefault(attachment.message_id, []).append(
            AttachmentOut(
                id=attachment.id,
                filename=attachment.filename,
                content_type=attachment.content_type,
                size_bytes=attachment.size_bytes,
                created_at=attachment.created_at,
            )
        )

    result: list[MessageOut] = []
    for message in messages:
        sender = senders.get(message.sender_member_id)
        if sender is None:
            continue
        result.append(
            MessageOut(
                id=message.id,
                group_id=message.group_id,
                sender=MemberRef(
                    id=sender.id,
                    display_name=sender.display_name,
                    member_type=sender.member_type,
                ),
                content=message.content,
                content_type=message.content_type,
                parent_message_id=message.parent_message_id,
                mentions=mentions.get(message.id, []),
                attachments=attachment_map.get(message.id, []),
                metadata=message.metadata_,
                created_at=message.created_at,
                edited_at=message.edited_at,
            )
        )
    return result


async def _unread_count(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    group_id: uuid.UUID,
    member_id: uuid.UUID,
    last_read_at: datetime | None,
) -> int:
    statement = (
        select(func.count())
        .select_from(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.group_id == group_id,
            Message.sender_member_id != member_id,
            Message.deleted_at.is_(None),
        )
    )
    if last_read_at is not None:
        statement = statement.where(Message.created_at > last_read_at)
    return int(await session.scalar(statement) or 0)


async def list_groups(
    session: AsyncSession, tenant_id: uuid.UUID, member_id: uuid.UUID
) -> list[GroupOut]:
    rows = (
        await session.execute(
            select(Group, GroupMember)
            .join(
                GroupMember,
                (GroupMember.group_id == Group.id) & (GroupMember.tenant_id == Group.tenant_id),
            )
            .where(GroupMember.tenant_id == tenant_id, GroupMember.member_id == member_id)
            .order_by(Group.updated_at.desc())
        )
    ).all()
    result: list[GroupOut] = []
    for group, membership in rows:
        members = await _group_members(session, tenant_id, group.id)
        last = await session.scalar(
            select(Message)
            .where(
                Message.tenant_id == tenant_id,
                Message.group_id == group.id,
                Message.deleted_at.is_(None),
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        last_out = (await _serialize_messages(session, tenant_id, [last]))[0] if last else None
        result.append(
            GroupOut(
                id=group.id,
                name=group.name,
                group_type=group.group_type,
                created_at=group.created_at,
                updated_at=group.updated_at,
                members=members,
                last_message=last_out,
                unread_count=await _unread_count(
                    session, tenant_id, group.id, member_id, membership.last_read_at
                ),
            )
        )
    return result


async def _member_or_error(
    session: AsyncSession, tenant_id: uuid.UUID, member_id: uuid.UUID
) -> Member:
    member = await session.scalar(
        select(Member).where(Member.tenant_id == tenant_id, Member.id == member_id)
    )
    if member is None or member.status != "active":
        raise ApiError(422, "invalid_member", "成员不存在或已停用")
    return member


async def create_group(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    creator: Member,
    *,
    name: str | None,
    group_type: str,
    member_ids: list[uuid.UUID],
) -> Group:
    unique_ids = {member_id for member_id in member_ids if member_id != creator.id}
    if group_type == "direct":
        if len(unique_ids) != 1:
            raise ApiError(422, "invalid_direct_chat", "单聊必须且只能指定一名对方成员")
        target_id = next(iter(unique_ids))
        existing = await session.scalar(
            text(
                """
                SELECT g.id
                FROM groups g
                JOIN group_members me ON me.group_id = g.id AND me.member_id = :me
                JOIN group_members other ON other.group_id = g.id AND other.member_id = :other
                WHERE g.tenant_id = :tenant_id
                  AND g.group_type = 'direct'
                  AND (SELECT count(*) FROM group_members gm WHERE gm.group_id = g.id) = 2
                LIMIT 1
                """
            ),
            {"me": str(creator.id), "other": str(target_id), "tenant_id": str(tenant_id)},
        )
        if existing is not None:
            group = await session.get(Group, existing)
            if group is not None:
                return group
    elif not name or not name.strip():
        raise ApiError(422, "group_name_required", "群聊名称不能为空")

    for member_id in unique_ids:
        await _member_or_error(session, tenant_id, member_id)

    group = Group(
        tenant_id=tenant_id,
        name=name.strip() if group_type == "channel" and name else None,
        group_type=group_type,
        created_by_member_id=creator.id,
    )
    session.add(group)
    await session.flush()
    session.add(
        GroupMember(tenant_id=tenant_id, group_id=group.id, member_id=creator.id, role="owner")
    )
    for member_id in unique_ids:
        session.add(
            GroupMember(tenant_id=tenant_id, group_id=group.id, member_id=member_id, role="member")
        )
    await session.flush()
    return group


async def add_members(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    group: Group,
    member_ids: list[uuid.UUID],
) -> None:
    existing = {
        membership.member_id
        for membership in (
            await session.scalars(
                select(GroupMember).where(
                    GroupMember.tenant_id == tenant_id, GroupMember.group_id == group.id
                )
            )
        ).all()
    }
    for member_id in member_ids:
        if member_id in existing:
            continue
        await _member_or_error(session, tenant_id, member_id)
        session.add(
            GroupMember(tenant_id=tenant_id, group_id=group.id, member_id=member_id, role="member")
        )
    await session.flush()


async def remove_member(
    session: AsyncSession, tenant_id: uuid.UUID, group: Group, member_id: uuid.UUID
) -> None:
    membership = await session.scalar(
        select(GroupMember).where(
            GroupMember.tenant_id == tenant_id,
            GroupMember.group_id == group.id,
            GroupMember.member_id == member_id,
        )
    )
    if membership is None:
        raise ApiError(404, "group_member_not_found", "群成员不存在")
    if membership.role == "owner":
        owners = await session.scalar(
            select(func.count())
            .select_from(GroupMember)
            .where(
                GroupMember.tenant_id == tenant_id,
                GroupMember.group_id == group.id,
                GroupMember.role == "owner",
            )
        )
        if owners <= 1:
            raise ApiError(409, "last_group_owner", "群聊必须至少保留一名管理员")
    await session.delete(membership)
    await session.flush()


async def list_messages(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    group_id: uuid.UUID,
    *,
    limit: int = 50,
    search: str | None = None,
) -> list[MessageOut]:
    statement = select(Message).where(
        Message.tenant_id == tenant_id,
        Message.group_id == group_id,
        Message.deleted_at.is_(None),
    )
    if search:
        statement = statement.where(Message.content.ilike(f"%{search.strip()}%"))
    messages = list(
        (await session.scalars(statement.order_by(Message.created_at.desc()).limit(limit))).all()
    )
    messages.reverse()
    return await _serialize_messages(session, tenant_id, messages)


async def create_message(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    group: Group,
    sender: Member,
    *,
    content: str,
    parent_message_id: uuid.UUID | None,
    mention_member_ids: list[uuid.UUID],
    attachment_ids: list[uuid.UUID],
) -> tuple[MessageOut, list[uuid.UUID]]:
    text_content = content.strip()
    if not text_content and not attachment_ids:
        raise ApiError(422, "empty_message", "消息内容不能为空")
    if parent_message_id is not None:
        parent = await session.scalar(
            select(Message).where(
                Message.tenant_id == tenant_id,
                Message.group_id == group.id,
                Message.id == parent_message_id,
            )
        )
        if parent is None:
            raise ApiError(422, "invalid_parent", "引用的消息不存在")

    members = (
        await session.scalars(
            select(Member).where(
                Member.tenant_id == tenant_id,
                Member.id.in_(
                    [
                        membership.member_id
                        for membership in (
                            await session.scalars(
                                select(GroupMember).where(
                                    GroupMember.tenant_id == tenant_id,
                                    GroupMember.group_id == group.id,
                                )
                            )
                        ).all()
                    ]
                ),
            )
        )
    ).all()
    member_map = {member.id: member for member in members}

    if any(member_id not in member_map for member_id in mention_member_ids):
        raise ApiError(422, "invalid_mentions", "被提及成员不在群聊中")

    # Explicit mentions plus @DisplayName detection (longest name first).
    detected = set(mention_member_ids)
    for member in sorted(members, key=lambda item: len(item.display_name), reverse=True):
        if member.id == sender.id:
            continue
        if f"@{member.display_name}" in text_content:
            detected.add(member.id)

    attachments: list[Attachment] = []
    if attachment_ids:
        attachments = list(
            (
                await session.scalars(
                    select(Attachment).where(
                        Attachment.tenant_id == tenant_id,
                        Attachment.group_id == group.id,
                        Attachment.id.in_(attachment_ids),
                        Attachment.uploader_member_id == sender.id,
                        Attachment.message_id.is_(None),
                    )
                )
            ).all()
        )
        if len(attachments) != len(set(attachment_ids)):
            raise ApiError(422, "invalid_attachments", "附件不存在或已被使用")

    message = Message(
        tenant_id=tenant_id,
        group_id=group.id,
        sender_member_id=sender.id,
        parent_message_id=parent_message_id,
        content=text_content,
        content_type="text",
    )
    session.add(message)
    await session.flush()

    for member_id in detected:
        session.add(MessageMention(tenant_id=tenant_id, message_id=message.id, member_id=member_id))
    for attachment in attachments:
        attachment.message_id = message.id
    group.updated_at = datetime.now(UTC)
    await session.flush()

    serialized = (await _serialize_messages(session, tenant_id, [message]))[0]
    mentioned_ai = [
        member_id
        for member_id in detected
        if member_map.get(member_id) is not None
        and member_map[member_id].member_type == "ai"
        and member_map[member_id].ai_enabled
    ]
    return serialized, mentioned_ai


async def mark_read(
    session: AsyncSession, tenant_id: uuid.UUID, group_id: uuid.UUID, member_id: uuid.UUID
) -> None:
    membership = await session.scalar(
        select(GroupMember).where(
            GroupMember.tenant_id == tenant_id,
            GroupMember.group_id == group_id,
            GroupMember.member_id == member_id,
        )
    )
    if membership is None:
        raise ApiError(404, "group_not_found", "群聊不存在")
    membership.last_read_at = datetime.now(UTC)
    await session.flush()


def event_channel(tenant_id: uuid.UUID) -> str:
    return f"orgweave:events:tenant:{tenant_id}"


async def publish_message_event(
    redis: Redis,
    *,
    tenant_id: uuid.UUID,
    message: MessageOut,
    mentioned_ai_ids: list[uuid.UUID],
) -> None:
    await redis.publish(
        event_channel(tenant_id),
        json.dumps(
            {
                "type": "message.created",
                "tenant_id": str(tenant_id),
                "group_id": str(message.group_id),
                "message": message.model_dump(mode="json"),
                "mentioned_ai_ids": [str(member_id) for member_id in mentioned_ai_ids],
            },
            ensure_ascii=False,
        ),
    )


async def group_detail(
    session: AsyncSession, tenant_id: uuid.UUID, group: Group, member_id: uuid.UUID
) -> GroupOut:
    members = await _group_members(session, tenant_id, group.id)
    membership = await session.scalar(
        select(GroupMember).where(
            GroupMember.tenant_id == tenant_id,
            GroupMember.group_id == group.id,
            GroupMember.member_id == member_id,
        )
    )
    last = await session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.group_id == group.id,
            Message.deleted_at.is_(None),
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    last_out = (await _serialize_messages(session, tenant_id, [last]))[0] if last else None
    return GroupOut(
        id=group.id,
        name=group.name,
        group_type=group.group_type,
        created_at=group.created_at,
        updated_at=group.updated_at,
        members=members,
        last_message=last_out,
        unread_count=await _unread_count(
            session, tenant_id, group.id, member_id, membership.last_read_at if membership else None
        ),
    )
