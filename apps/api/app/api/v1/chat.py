"""Chat REST API: groups, messages, read state and attachments."""

from __future__ import annotations

import asyncio
import io
import logging
import uuid
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import iterate_in_threadpool

from app.api.deps import (
    TenantContext,
    get_session,
    get_tenant_context,
    set_tenant_context,
)
from app.application.audit import record_audit
from app.application.chat import (
    add_members,
    create_group,
    create_message,
    group_detail,
    list_groups,
    list_messages,
    mark_read,
    publish_message_event,
    remove_member,
    require_membership,
)
from app.core.errors import ApiError
from app.models import Attachment, GroupMember
from app.schemas.chat import (
    AttachmentOut,
    GroupCreate,
    GroupMembersUpdate,
    GroupOut,
    GroupUpdate,
    MessageCreate,
    MessageOut,
)

logger = logging.getLogger("orgweave.chat")
router = APIRouter(tags=["chat"])

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "application/pdf",
    "text/plain",
    "text/markdown",
    "application/json",
    "application/zip",
    "application/octet-stream",
}


def _can_manage_group(context: TenantContext, membership: GroupMember) -> bool:
    return membership.role == "owner" or "member.manage" in context.permissions


@router.get("/groups", response_model=list[GroupOut], summary="List groups for current member")
async def get_groups(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[GroupOut]:
    result = await list_groups(session, context.tenant_id, context.member.id)
    await session.commit()
    return result


@router.post(
    "/groups",
    response_model=GroupOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a channel or direct chat",
)
async def post_group(
    body: GroupCreate,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GroupOut:
    try:
        group = await create_group(
            session,
            context.tenant_id,
            context.member,
            name=body.name,
            group_type=body.group_type,
            member_ids=body.member_ids,
        )
    except IntegrityError as exc:
        await session.rollback()
        raise ApiError(409, "group_conflict", "群聊创建冲突") from exc
    await session.commit()
    await set_tenant_context(session, context.tenant_id)
    result = await group_detail(session, context.tenant_id, group, context.member.id)
    await session.commit()
    return result


@router.get("/groups/{group_id}", response_model=GroupOut, summary="Get a group")
async def get_group(
    group_id: uuid.UUID,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GroupOut:
    group, _ = await require_membership(session, context.tenant_id, group_id, context.member.id)
    result = await group_detail(session, context.tenant_id, group, context.member.id)
    await session.commit()
    return result


@router.patch("/groups/{group_id}", response_model=GroupOut, summary="Rename a group")
async def patch_group(
    group_id: uuid.UUID,
    body: GroupUpdate,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GroupOut:
    group, membership = await require_membership(
        session, context.tenant_id, group_id, context.member.id
    )
    if not _can_manage_group(context, membership):
        raise ApiError(403, "group_forbidden", "无权管理该群聊")
    if group.group_type == "direct":
        raise ApiError(422, "direct_chat_rename", "单聊不能重命名")
    group.name = body.name.strip()
    record_audit(
        session,
        tenant_id=context.tenant_id,
        actor_type="member",
        actor_id=context.member.id,
        action="group.renamed",
        resource_type="group",
        resource_id=group.id,
        metadata={"name": group.name},
    )
    await session.commit()
    await set_tenant_context(session, context.tenant_id)
    result = await group_detail(session, context.tenant_id, group, context.member.id)
    await session.commit()
    return result


@router.post(
    "/groups/{group_id}/members",
    response_model=GroupOut,
    summary="Add members to a group",
)
async def post_group_members(
    group_id: uuid.UUID,
    body: GroupMembersUpdate,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GroupOut:
    group, membership = await require_membership(
        session, context.tenant_id, group_id, context.member.id
    )
    if not _can_manage_group(context, membership):
        raise ApiError(403, "group_forbidden", "无权管理该群聊")
    if group.group_type == "direct":
        raise ApiError(422, "direct_chat_members", "单聊不能添加成员")
    await add_members(session, context.tenant_id, group, body.member_ids)
    record_audit(
        session,
        tenant_id=context.tenant_id,
        actor_type="member",
        actor_id=context.member.id,
        action="group.members_added",
        resource_type="group",
        resource_id=group.id,
        metadata={"member_ids": [str(member_id) for member_id in body.member_ids]},
    )
    await session.commit()
    await set_tenant_context(session, context.tenant_id)
    result = await group_detail(session, context.tenant_id, group, context.member.id)
    await session.commit()
    return result


@router.delete(
    "/groups/{group_id}/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a member from a group",
)
async def delete_group_member(
    group_id: uuid.UUID,
    member_id: uuid.UUID,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    group, membership = await require_membership(
        session, context.tenant_id, group_id, context.member.id
    )
    if member_id != context.member.id and not _can_manage_group(context, membership):
        raise ApiError(403, "group_forbidden", "无权管理该群聊")
    await remove_member(session, context.tenant_id, group, member_id)
    record_audit(
        session,
        tenant_id=context.tenant_id,
        actor_type="member",
        actor_id=context.member.id,
        action="group.member_removed",
        resource_type="group",
        resource_id=group.id,
        metadata={"member_id": str(member_id)},
    )
    await session.commit()


@router.get(
    "/groups/{group_id}/messages",
    response_model=list[MessageOut],
    summary="Message history (oldest to newest)",
)
async def get_messages(
    group_id: uuid.UUID,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> list[MessageOut]:
    await require_membership(session, context.tenant_id, group_id, context.member.id)
    result = await list_messages(session, context.tenant_id, group_id, limit=limit, search=search)
    await session.commit()
    return result


@router.post(
    "/groups/{group_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Send a message",
)
async def post_message(
    group_id: uuid.UUID,
    body: MessageCreate,
    request: Request,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MessageOut:
    group, _ = await require_membership(session, context.tenant_id, group_id, context.member.id)
    message, mentioned_ai_ids = await create_message(
        session,
        context.tenant_id,
        group,
        context.member,
        content=body.content,
        parent_message_id=body.parent_message_id,
        mention_member_ids=body.mention_member_ids,
        attachment_ids=body.attachment_ids,
    )
    await session.commit()
    try:
        await publish_message_event(
            request.app.state.redis,
            tenant_id=context.tenant_id,
            message=message,
            mentioned_ai_ids=mentioned_ai_ids,
        )
    except Exception:
        logger.exception("failed to publish message event")
    return message


@router.post(
    "/groups/{group_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark a group as read",
)
async def post_read(
    group_id: uuid.UUID,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    await require_membership(session, context.tenant_id, group_id, context.member.id)
    await mark_read(session, context.tenant_id, group_id, context.member.id)
    await session.commit()


@router.post(
    "/groups/{group_id}/attachments",
    response_model=AttachmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an attachment to a group (max 10 MiB)",
)
async def upload_attachment(
    group_id: uuid.UUID,
    request: Request,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
    file: Annotated[UploadFile, File()],
) -> AttachmentOut:
    await require_membership(session, context.tenant_id, group_id, context.member.id)
    data = await file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise ApiError(413, "attachment_too_large", "附件不能超过 10 MiB")
    if not data:
        raise ApiError(422, "empty_attachment", "附件为空")
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ApiError(415, "unsupported_attachment_type", f"不支持的附件类型：{content_type}")
    filename = Path(file.filename or "attachment").name[:255]
    object_key = (
        f"{context.tenant_id}/groups/{group_id}/" f"{uuid.uuid4().hex}-{filename.replace(' ', '_')}"
    )
    settings = request.app.state.settings
    minio_client = request.app.state.minio
    try:
        await asyncio.to_thread(
            minio_client.put_object,
            settings.minio_bucket,
            object_key,
            io.BytesIO(data),
            len(data),
            content_type=content_type,
        )
    except Exception as exc:
        raise ApiError(502, "storage_unavailable", "对象存储写入失败") from exc

    attachment = Attachment(
        tenant_id=context.tenant_id,
        group_id=group_id,
        uploader_member_id=context.member.id,
        object_key=object_key,
        filename=filename,
        content_type=content_type,
        size_bytes=len(data),
    )
    session.add(attachment)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiError(409, "attachment_conflict", "附件写入冲突") from exc
    record_audit(
        session,
        tenant_id=context.tenant_id,
        actor_type="member",
        actor_id=context.member.id,
        action="attachment.uploaded",
        resource_type="attachment",
        resource_id=attachment.id,
        metadata={"filename": filename, "size_bytes": len(data)},
    )
    await session.commit()
    return AttachmentOut(
        id=attachment.id,
        filename=attachment.filename,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        created_at=attachment.created_at,
    )


@router.get(
    "/attachments/{attachment_id}",
    summary="Download an attachment (streamed, permission-checked)",
)
async def download_attachment(
    attachment_id: uuid.UUID,
    request: Request,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StreamingResponse:
    attachment = await session.scalar(
        select(Attachment).where(
            Attachment.tenant_id == context.tenant_id, Attachment.id == attachment_id
        )
    )
    if attachment is None:
        raise ApiError(404, "attachment_not_found", "附件不存在")
    await require_membership(session, context.tenant_id, attachment.group_id, context.member.id)
    settings = request.app.state.settings
    try:
        upstream = await asyncio.to_thread(
            request.app.state.minio.get_object,
            settings.minio_bucket,
            attachment.object_key,
        )
    except Exception as exc:
        raise ApiError(502, "storage_unavailable", "附件读取失败") from exc

    async def stream_body():
        try:
            async for chunk in iterate_in_threadpool(upstream.stream(64 * 1024)):
                yield chunk
        finally:
            await asyncio.to_thread(upstream.close)

    safe_filename = attachment.filename.replace('"', "_")
    await session.commit()
    return StreamingResponse(
        stream_body(),
        media_type=attachment.content_type,
        headers={
            "Content-Length": str(attachment.size_bytes),
            "Content-Disposition": (
                f'attachment; filename="download"; ' f"filename*=UTF-8''{quote(safe_filename)}"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )
