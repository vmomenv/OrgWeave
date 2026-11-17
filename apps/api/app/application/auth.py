"""Authentication application service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models import RefreshToken, User


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def register_user(
    session: AsyncSession, *, email: str, password: str, display_name: str
) -> User:
    normalized = normalize_email(email)
    existing = await session.scalar(select(User.id).where(User.email == normalized))
    if existing is not None:
        raise ApiError(409, "email_taken", "该邮箱已注册")
    user = User(
        email=normalized,
        password_hash=hash_password(password),
        display_name=display_name.strip(),
    )
    session.add(user)
    await session.flush()
    return user


async def authenticate_user(session: AsyncSession, *, email: str, password: str) -> User | None:
    user = await session.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        verify_password(password, None)  # timing equalization
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def issue_tokens(session: AsyncSession, user: User) -> dict[str, object]:
    settings = get_settings()
    raw_refresh = generate_refresh_token()
    expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days)
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(raw_refresh),
            expires_at=expires_at,
        )
    )
    await session.flush()
    return {
        "access_token": create_access_token(user.id),
        "refresh_token": raw_refresh,
        "token_type": "bearer",
        "expires_in": settings.access_token_ttl_seconds,
    }


def refresh_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=get_settings().refresh_token_ttl_days)


async def rotate_refresh_token(session: AsyncSession, raw_token: str) -> tuple[User, dict]:
    token = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token))
    )
    now = datetime.now(UTC)
    if token is None or token.revoked_at is not None or token.expires_at <= now:
        raise ApiError(401, "invalid_refresh_token", "刷新令牌无效或已过期")
    user = await session.get(User, token.user_id)
    if user is None or not user.is_active:
        raise ApiError(401, "invalid_refresh_token", "刷新令牌无效或已过期")

    token.revoked_at = now
    tokens = await issue_tokens(session, user)
    return user, tokens


async def revoke_refresh_token(session: AsyncSession, raw_token: str) -> bool:
    token = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token))
    )
    if token is None or token.revoked_at is not None:
        return False
    token.revoked_at = datetime.now(UTC)
    return True


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)
