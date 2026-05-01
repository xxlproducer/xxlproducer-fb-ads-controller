"""Application configuration loaded from environment / .env.

We keep a single source of truth in `Settings` and read it everywhere via the
imported `settings` instance. The defaults are tuned for local single-user
development on Windows; everything is overridable via environment variables.
"""
from __future__ import annotations

import secrets
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="FBAC_",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------ paths
    data_dir: Path = Field(default_factory=lambda: Path("data"))

    # ------------------------------------------------------------------- core
    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(48))
    admin_username: str = "admin"
    # `admin_password` is set on first run via /api/auth/setup if no users exist
    fb_api_version: str = "v21.0"

    # ----------------------------------------------------------------- server
    host: str = "127.0.0.1"
    port: int = 8080
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @property
    def db_path(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir / "fb_ads_controller.db"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path.as_posix()}"

    @property
    def uploads_dir(self) -> Path:
        d = self.data_dir / "uploads"
        d.mkdir(parents=True, exist_ok=True)
        return d


settings = Settings()
