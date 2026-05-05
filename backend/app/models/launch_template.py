"""Saved launch templates for the Autozaliv wizard.

A template captures everything needed to spin up Campaign + AdSet on any
ad account: objective, budget, optimization, targeting, bidding, etc.
The actual FB-side parameters live in `config` as JSON so we can evolve
the schema without database migrations.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LaunchTemplate(Base):
    __tablename__ = "launch_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # JSON-encoded campaign + adset config (see schemas/launch.py for shape).
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

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

    def get_config(self) -> dict[str, Any]:
        try:
            return json.loads(self.config_json)
        except (TypeError, ValueError):
            return {}

    def set_config(self, value: dict[str, Any]) -> None:
        self.config_json = json.dumps(value, ensure_ascii=False)
