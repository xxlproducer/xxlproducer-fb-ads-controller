"""SQLAlchemy declarative base + table creation."""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase

from app.db.session import engine


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    # Importing models registers them on Base.metadata
    from app.models import (  # noqa: F401
        bulk_action_log,
        creative,
        fb_token,
        launch_template,
        user,
    )

    Base.metadata.create_all(bind=engine)
