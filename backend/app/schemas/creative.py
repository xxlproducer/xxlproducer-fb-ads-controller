"""Pydantic schemas for creatives + bulk Ad creation."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreativeOut(BaseModel):
    id: int
    name: str
    media_type: str
    media_filename: str
    media_mime: str | None = None
    thumbnail_filename: str | None = None
    title: str | None = None
    body: str | None = None
    description: str | None = None
    link_url: str | None = None
    cta_type: str | None = None
    page_id: str | None = None
    instagram_actor_id: str | None = None
    created_at: datetime
    updated_at: datetime


class CreativeUpdate(BaseModel):
    name: str | None = None
    title: str | None = None
    body: str | None = None
    description: str | None = None
    link_url: str | None = None
    cta_type: str | None = None
    page_id: str | None = None
    instagram_actor_id: str | None = None


class AdTarget(BaseModel):
    """One destination AdSet for a bulk Ad-create call."""

    token_id: int
    ad_account_id: str  # may include or omit "act_" prefix
    adset_id: str
    ad_name: str | None = None  # optional override; defaults to creative name


class BulkCreateAdsRequest(BaseModel):
    creative_id: int
    targets: list[AdTarget] = Field(default_factory=list)
    status: str = "PAUSED"  # PAUSED | ACTIVE


class AdResult(BaseModel):
    token_id: int
    ad_account_id: str
    adset_id: str
    success: bool
    ad_id: str | None = None
    creative_id_fb: str | None = None
    image_hash: str | None = None
    video_id: str | None = None
    error: str | None = None


class BulkCreateAdsResponse(BaseModel):
    total: int
    succeeded: int
    failed: int
    results: list[AdResult]
