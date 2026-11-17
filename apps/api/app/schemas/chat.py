"""Chat request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class GroupCreate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    group_type: Literal["channel", "direct"] = "channel"
    member_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)


class GroupUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class GroupMemberOut(BaseModel):
    member_id: uuid.UUID
    display_name: str
    member_type: str
    title: str | None = None
    role: str
    joined_at: datetime
    last_read_at: datetime | None = None


class MemberRef(BaseModel):
    id: uuid.UUID
    display_name: str
    member_type: str


class AttachmentOut(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class MessageOut(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    sender: MemberRef
    content: str
    content_type: str
    parent_message_id: uuid.UUID | None
    mentions: list[MemberRef] = Field(default_factory=list)
    attachments: list[AttachmentOut] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    edited_at: datetime | None = None


class MessageCreate(BaseModel):
    content: str = Field(default="", max_length=8000)
    parent_message_id: uuid.UUID | None = None
    mention_member_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    attachment_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)


class GroupOut(BaseModel):
    id: uuid.UUID
    name: str | None
    group_type: str
    created_at: datetime
    updated_at: datetime
    members: list[GroupMemberOut] = Field(default_factory=list)
    last_message: MessageOut | None = None
    unread_count: int = 0


class GroupMembersUpdate(BaseModel):
    member_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class ReadUpdate(BaseModel):
    pass


class ChatEvent(BaseModel):
    type: str
    tenant_id: uuid.UUID
    group_id: uuid.UUID
    message: MessageOut | None = None
    mentioned_ai_ids: list[uuid.UUID] = Field(default_factory=list)
