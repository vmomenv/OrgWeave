"""Tenant and organization schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str | None = Field(default=None, min_length=2, max_length=60, pattern=r"^[a-z0-9-]+$")


class TenantUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime


class CurrentTenantOut(TenantOut):
    membership_status: str
    member_id: uuid.UUID
    member_display_name: str
    role_keys: list[str]
    permissions: list[str]


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: uuid.UUID | None = None


class DepartmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    parent_id: uuid.UUID | None = None


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class RoleSummary(BaseModel):
    key: str
    name: str


class PermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    description: str


class RoleOut(RoleSummary):
    description: str
    is_system: bool
    permissions: list[str]


class MemberCreate(BaseModel):
    member_type: Literal["human", "ai"]
    user_id: uuid.UUID | None = None
    display_name: str = Field(min_length=1, max_length=120)
    title: str | None = Field(default=None, max_length=120)
    bio: str | None = Field(default=None, max_length=2000)
    avatar_url: str | None = Field(default=None, max_length=500)
    department_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None
    ai_enabled: bool = True
    role_keys: list[str] = Field(default_factory=lambda: ["member"])

    @model_validator(mode="after")
    def _identity_matches_type(self) -> MemberCreate:
        if self.member_type == "human" and self.user_id is None:
            raise ValueError("human members must reference a user_id")
        if self.member_type == "ai" and self.user_id is not None:
            raise ValueError("ai members must not reference a user_id")
        return self


class MemberUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    title: str | None = Field(default=None, max_length=120)
    bio: str | None = Field(default=None, max_length=2000)
    avatar_url: str | None = Field(default=None, max_length=500)
    department_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None
    status: Literal["active", "disabled"] | None = None
    ai_enabled: bool | None = None


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    member_type: str
    user_id: uuid.UUID | None
    display_name: str
    title: str | None
    bio: str | None
    avatar_url: str | None
    department_id: uuid.UUID | None
    manager_id: uuid.UUID | None
    status: str
    ai_enabled: bool
    created_at: datetime
    updated_at: datetime
    roles: list[RoleSummary] = Field(default_factory=list)


class MemberRolesUpdate(BaseModel):
    role_keys: list[str] = Field(min_length=1, max_length=10)


class InvitationCreate(BaseModel):
    email: EmailStr
    role_key: str = Field(default="member", min_length=2, max_length=40)


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role_key: str
    status: str
    expires_at: datetime
    created_at: datetime


class InvitationCreated(InvitationOut):
    token: str


class AcceptInvitationRequest(BaseModel):
    token: str = Field(min_length=16)


class AuditLogOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID | None
    actor_type: str
    actor_id: uuid.UUID | None
    action: str
    resource_type: str
    resource_id: uuid.UUID | None
    result: str
    metadata: dict
    created_at: datetime
