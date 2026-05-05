"""Pydantic schemas for the Autozaliv (launch wizard) API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# --- nested config ----------------------------------------------------------


class TargetingConfig(BaseModel):
    """Subset of FB targeting spec we expose to the user.

    Stored verbatim under templates and forwarded to /act_<id>/adsets.
    """

    countries: list[str] = Field(default_factory=list)
    age_min: int = 18
    age_max: int = 65
    genders: list[int] = Field(default_factory=list)  # [] = all, [1]=male, [2]=female
    locales: list[int] = Field(default_factory=list)
    publisher_platforms: list[str] = Field(default_factory=list)  # [] = all


class PromotedObject(BaseModel):
    pixel_id: str | None = None
    custom_event_type: str | None = None  # PURCHASE / LEAD / COMPLETE_REGISTRATION ...
    application_id: str | None = None
    object_store_url: str | None = None


class CampaignConfig(BaseModel):
    objective: str = "OUTCOME_SALES"
    status: Literal["PAUSED", "ACTIVE"] = "PAUSED"
    special_ad_categories: list[str] = Field(default_factory=list)
    buying_type: str = "AUCTION"

    daily_budget: float | None = None  # account currency units (e.g. PLN)
    lifetime_budget: float | None = None
    bid_strategy: str | None = None  # LOWEST_COST_WITHOUT_CAP / LOWEST_COST_WITH_BID_CAP / COST_CAP


class AdSetConfig(BaseModel):
    optimization_goal: str = "OFFSITE_CONVERSIONS"
    billing_event: str = "IMPRESSIONS"
    status: Literal["PAUSED", "ACTIVE"] = "PAUSED"

    daily_budget: float | None = None  # only when CBO is OFF at campaign level
    lifetime_budget: float | None = None
    bid_amount: float | None = None

    targeting: TargetingConfig = Field(default_factory=TargetingConfig)
    promoted_object: PromotedObject | None = None

    destination_type: str | None = None
    start_time: str | None = None
    end_time: str | None = None

    # EU Digital Services Act compliance — required for adsets targeting EU.
    # Free-text strings: name of the person/organization being advertised.
    dsa_beneficiary: str | None = None
    dsa_payor: str | None = None


class TemplateConfig(BaseModel):
    """Top-level template config persisted under LaunchTemplate.config_json."""

    campaign: CampaignConfig = Field(default_factory=CampaignConfig)
    adset: AdSetConfig = Field(default_factory=AdSetConfig)


# --- request / response models ---------------------------------------------


class TemplateCreate(BaseModel):
    name: str
    description: str | None = None
    config: TemplateConfig = Field(default_factory=TemplateConfig)


class TemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    config: TemplateConfig | None = None


class TemplateOut(BaseModel):
    id: int
    name: str
    description: str | None
    config: TemplateConfig
    created_at: datetime
    updated_at: datetime


class AccountTarget(BaseModel):
    """Reference to one (token, ad-account) pair from /api/fb-accounts."""

    token_id: int
    account_id: str  # without `act_` prefix


class LaunchRequest(BaseModel):
    template_id: int
    targets: list[AccountTarget]
    # Optional name overrides — defaults to template name + " - <account name>"
    campaign_name: str | None = None
    adset_name: str | None = None


class PreviewRow(BaseModel):
    token_id: int
    account_id: str
    account_name: str | None = None
    currency: str | None = None
    campaign_name: str
    adset_name: str
    objective: str
    daily_budget: float | None
    optimization_goal: str
    targeting_summary: str


class PreviewResponse(BaseModel):
    plan: list[PreviewRow]
    warnings: list[str] = Field(default_factory=list)


class LaunchResult(BaseModel):
    token_id: int
    account_id: str
    ok: bool
    campaign_id: str | None = None
    adset_id: str | None = None
    error: str | None = None


class LaunchResponse(BaseModel):
    results: list[LaunchResult]


# --- account health (pixels + pages) ---------------------------------------


class PixelInfo(BaseModel):
    id: str
    name: str | None = None
    is_unavailable: bool = False
    last_fired_time: str | None = None


class PageInfo(BaseModel):
    id: str
    name: str | None = None


class AccountHealth(BaseModel):
    """What we tell the UI about a single (token, ad-account) target.

    Used by Step 2 / 3 of the launch wizard to gate the Sales / Leads
    presets on accounts that don't have a Pixel yet (FB error messages
    for that case are notoriously misleading).
    """

    token_id: int
    account_id: str
    account_name: str | None = None
    has_pixel: bool
    has_page: bool
    pixels: list[PixelInfo] = Field(default_factory=list)
    pages: list[PageInfo] = Field(default_factory=list)
    error: str | None = None


class AccountHealthRequest(BaseModel):
    targets: list[AccountTarget]


class AccountHealthResponse(BaseModel):
    accounts: list[AccountHealth]
