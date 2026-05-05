"""Pydantic schemas for the Autozaliv (launch wizard) API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# --- nested config ----------------------------------------------------------


class GeoEntry(BaseModel):
    """One picked FB geo location.

    Mirrors the rows returned by FB's `GET /search?type=adgeolocation`
    endpoint, keeping enough metadata to render the picker without a
    re-lookup AND to serialise back into FB's targeting `geo_locations`
    structure on launch.
    """

    key: str  # "PL" / "US" / numeric region/city id
    type: str  # "country" | "country_group" | "region" | "city" | ...
    name: str | None = None
    country_code: str | None = None
    country_name: str | None = None
    region: str | None = None
    region_id: int | None = None


class TargetingConfig(BaseModel):
    """Subset of FB targeting spec we expose to the user.

    Stored verbatim under templates and forwarded to /act_<id>/adsets.
    """

    countries: list[str] = Field(default_factory=list)
    # Live FB-validated entries. When non-empty this REPLACES `countries`
    # in the FB targeting payload, since FB picker covers regions/cities
    # too. `countries` stays for backwards-compatible templates.
    geo_locations_picked: list[GeoEntry] = Field(default_factory=list)
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


# --- v2 launch (full Campaign + AdSet + Ad with topology + creatives) -----


class Topology(BaseModel):
    """How many of each level to create per (token, ad-account) target."""

    n_campaigns: int = Field(default=1, ge=1, le=20)
    n_adsets_per_campaign: int = Field(default=1, ge=1, le=20)
    n_ads_per_adset: int = Field(default=0, ge=0, le=20)
    # n_ads_per_adset = 0 means "no Ads created, only Campaign + AdSet skeleton"
    # (= legacy MVP behavior; ad creation needs creatives selected).


class CreativeDistribution(BaseModel):
    """How creatives map onto Ads in the topology.

    `creative_ids` are local Creative.id values from /api/creatives.

    mode:
      * broadcast    — one creative cloned to all Ads.
      * round_robin  — cycle through creatives across Ads (1->ad1, 2->ad2,
                       3->ad3, 1->ad4, ...). Default and most flexible.
      * one_per_ad   — strict: requires len(creative_ids) == total_ads,
                       mapped 1:1 in order.
    """

    mode: Literal["broadcast", "round_robin", "one_per_ad"] = "round_robin"
    creative_ids: list[int] = Field(default_factory=list)


class LaunchRequestV2(BaseModel):
    template_id: int
    targets: list[AccountTarget]

    topology: Topology = Field(default_factory=Topology)
    distribution: CreativeDistribution | None = None

    # "{token_id}:{account_id}" -> page_id, only relevant when n_ads_per_adset>0
    page_id_per_account: dict[str, str] = Field(default_factory=dict)

    # "{token_id}:{account_id}" -> pixel_id, used to override the template's
    # promoted_object.pixel_id per account (Sales / Leads / Conversions).
    # When set for an account it takes precedence; otherwise falls back to
    # the template's pixel_id (if any).
    pixel_id_per_account: dict[str, str] = Field(default_factory=dict)

    # Name patterns. Available placeholders:
    #   {tpl}     — template name
    #   {account} — ad account name (or id if no name)
    #   {c}       — 1-based campaign index
    #   {a}       — 1-based adset index
    #   {k}       — 1-based ad index
    campaign_name_pattern: str | None = None
    adset_name_pattern: str | None = None
    ad_name_pattern: str | None = None

    # Status for created Ads (Campaign / AdSet status comes from template).
    ad_status: Literal["PAUSED", "ACTIVE"] = "PAUSED"


class AdResultV2(BaseModel):
    name: str
    creative_id: int | None = None  # local Creative.id used
    fb_creative_id: str | None = None
    ad_id: str | None = None
    error: str | None = None


class AdSetResultV2(BaseModel):
    name: str
    adset_id: str | None = None
    error: str | None = None
    ads: list[AdResultV2] = Field(default_factory=list)


class CampaignResultV2(BaseModel):
    name: str
    campaign_id: str | None = None
    error: str | None = None
    adsets: list[AdSetResultV2] = Field(default_factory=list)


class LaunchResultV2(BaseModel):
    token_id: int
    account_id: str
    ok: bool
    error: str | None = None
    campaigns: list[CampaignResultV2] = Field(default_factory=list)


class LaunchResponseV2(BaseModel):
    results: list[LaunchResultV2]
    summary: dict[str, int] = Field(default_factory=dict)
    # summary contains: campaigns_ok, campaigns_failed, adsets_ok,
    # adsets_failed, ads_ok, ads_failed
