"""Stored Facebook access tokens.

For now we store the long-lived user token + metadata returned by
`/me/permissions`, `/me`, and `/me/adaccounts`. The token value itself is
stored in plain text in the local SQLite DB — this is a single-user local
tool, but if we ever ship a hosted version we'll switch to encryption-at-rest.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FbToken(Base):
    __tablename__ = "fb_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # FB user identity (filled in on first sync)
    fb_user_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    fb_user_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # User-supplied label (e.g. "Farm acc #3")
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # The long-lived user token
    access_token: Mapped[str] = mapped_column(Text, nullable=False)

    # Comma-separated permission names that came back from /me/permissions
    granted_scopes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status: "active", "invalid", "expired"
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional proxy URL used for FB calls with this token
    proxy_url: Mapped[str | None] = mapped_column(String(255), nullable=True)

    is_disabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
