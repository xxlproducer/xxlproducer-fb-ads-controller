"""Reusable ad creative spec.

A `Creative` row captures the user-facing creative concept (one image or
video + headline / body / link / CTA / page). It does NOT carry per-FB-account
state on its own — image_hash / video_id are obtained per-account at ad
creation time and cached in `account_assets` so we don't re-upload the same
file to the same account.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Creative(Base):
    __tablename__ = "creatives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # "image" | "video"
    media_type: Mapped[str] = mapped_column(String(16), nullable=False, default="image")

    # Path on local disk relative to settings.uploads_dir (just the filename).
    media_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    media_mime: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Optional separate thumbnail file for videos (filename relative to uploads_dir)
    thumbnail_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Ad copy
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    link_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    cta_type: Mapped[str | None] = mapped_column(String(64), nullable=True, default="LEARN_MORE")

    # Identity for the ad object_story_spec
    page_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    instagram_actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Cached per-account uploads: { "act_X": {"image_hash": "..." | "video_id": "..."} }
    account_assets_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def get_account_assets(self) -> dict[str, dict[str, Any]]:
        try:
            return json.loads(self.account_assets_json)
        except (TypeError, ValueError):
            return {}

    def set_account_assets(self, value: dict[str, dict[str, Any]]) -> None:
        self.account_assets_json = json.dumps(value, ensure_ascii=False)
