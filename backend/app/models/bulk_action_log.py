"""Audit log of bulk actions performed against FB objects.

Lets us reconstruct what was paused/activated/deleted, when, and against
which objects — useful for ad-hoc debugging and a future "undo" feature.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BulkActionLog(Base):
    __tablename__ = "bulk_action_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # "pause", "activate", "archive", "delete"
    action: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # "campaign", "adset", "ad"
    level: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    token_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    account_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    object_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # "ok" or "error"
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
