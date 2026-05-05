"""Autozaliv (launch wizard) endpoints.

Lets the user save reusable Campaign + AdSet templates and spin them up
across many ad accounts in one go.

Note: ad creation (with creatives) lives in a follow-up iteration. This
module only creates Campaign + AdSet stubs; you then run real ads either
via Bulk Actions or by uploading creatives separately.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user
from app.models.bulk_action_log import BulkActionLog
from app.models.fb_token import FbToken
from app.models.launch_template import LaunchTemplate
from app.models.user import User
from app.core.config import settings
from app.models.creative import Creative
from app.schemas.launch import (
    AccountHealth,
    AccountHealthRequest,
    AccountHealthResponse,
    AccountTarget,
    AdResultV2,
    AdSetResultV2,
    CampaignResultV2,
    CreativeDistribution,
    LaunchRequest,
    LaunchRequestV2,
    LaunchResponse,
    LaunchResponseV2,
    LaunchResult,
    LaunchResultV2,
    PageInfo,
    PixelInfo,
    PreviewResponse,
    PreviewRow,
    TemplateConfig,
    TemplateCreate,
    TemplateOut,
    TemplateUpdate,
    Topology,
)
from app.services.fb_client import FbApiError, FbClient

logger = logging.getLogger(__name__)

router = APIRouter()

LAUNCH_CONCURRENCY = 3  # FB rate-limits creation more aggressively than reads.


# ===================================================================
#                            Templates CRUD
# ===================================================================


def _to_out(t: LaunchTemplate) -> TemplateOut:
    cfg = TemplateConfig.model_validate(t.get_config() or {})
    return TemplateOut(
        id=t.id,
        name=t.name,
        description=t.description,
        config=cfg,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


@router.get("/templates", response_model=list[TemplateOut])
def list_templates(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[TemplateOut]:
    rows = db.query(LaunchTemplate).order_by(LaunchTemplate.id.desc()).all()
    return [_to_out(t) for t in rows]


@router.post("/templates", response_model=TemplateOut, status_code=201)
def create_template(
    payload: TemplateCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> TemplateOut:
    t = LaunchTemplate(name=payload.name, description=payload.description)
    t.set_config(payload.config.model_dump())
    db.add(t)
    db.commit()
    db.refresh(t)
    return _to_out(t)


@router.get("/templates/{template_id}", response_model=TemplateOut)
def get_template(
    template_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> TemplateOut:
    t = db.get(LaunchTemplate, template_id)
    if not t:
        raise HTTPException(status_code=404, detail="template not found")
    return _to_out(t)


@router.put("/templates/{template_id}", response_model=TemplateOut)
def update_template(
    template_id: int,
    payload: TemplateUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> TemplateOut:
    t = db.get(LaunchTemplate, template_id)
    if not t:
        raise HTTPException(status_code=404, detail="template not found")
    if payload.name is not None:
        t.name = payload.name
    if payload.description is not None:
        t.description = payload.description
    if payload.config is not None:
        t.set_config(payload.config.model_dump())
    db.commit()
    db.refresh(t)
    return _to_out(t)


@router.delete("/templates/{template_id}")
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict[str, bool]:
    t = db.get(LaunchTemplate, template_id)
    if t:
        db.delete(t)
        db.commit()
    return {"ok": True}


# ===================================================================
#                          Account health
# ===================================================================


@router.post("/account_health", response_model=AccountHealthResponse)
async def account_health(
    request: AccountHealthRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> AccountHealthResponse:
    """Inspect each (token, ad-account) for Pixels and Pages.

    The launcher uses this to:
      * pre-fill a pixel dropdown (instead of asking the user to type
        a 16-digit pixel_id by hand);
      * block Sales / Leads templates on accounts with zero pixels
        BEFORE we hit the FB API and get a confusing error.
    """
    if not request.targets:
        return AccountHealthResponse(accounts=[])

    token_ids = {t.token_id for t in request.targets}
    tokens = _resolve_tokens(db, token_ids)
    return await _account_health(request, tokens)


# ===================================================================
#                       Geo targeting search
# ===================================================================


@router.get("/search_geo")
async def search_geo(
    q: str,
    token_id: int | None = None,
    location_types: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Live FB geo-targeting search.

    Returns the raw FB rows so the frontend can keep `key`, `country_code`,
    `country_name`, `name`, `type`, `region`, `region_id`, `supports_region`
    etc. and pass them straight back into a targeting spec.
    """
    if not q or len(q.strip()) < 2:
        return {"data": []}

    token = _pick_token(db, token_id)
    if token is None:
        raise HTTPException(status_code=400, detail="no FB token configured")

    types = [t.strip() for t in (location_types or "").split(",") if t.strip()] or None
    client = FbClient(token.access_token)
    rows = await client.search_geo(q.strip(), location_types=types)
    return {"data": rows}


@router.post("/lookup_geo")
async def lookup_geo(
    payload: dict,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Resolve a list of FB geo `key`s back into full geo records.

    Used to render existing template targeting (we only persist the FB
    `key` / `country_code` per row) into the picker without dropping
    metadata like `name` and `type`.
    """
    keys = payload.get("keys") or []
    token_id = payload.get("token_id")
    if not isinstance(keys, list) or not keys:
        return {"data": []}

    token = _pick_token(db, token_id if isinstance(token_id, int) else None)
    if token is None:
        raise HTTPException(status_code=400, detail="no FB token configured")

    client = FbClient(token.access_token)
    rows = await client.lookup_geo_by_keys([str(k) for k in keys])
    return {"data": rows}


def _pick_token(db: Session, token_id: int | None) -> FbToken | None:
    """Use the requested token if given, otherwise the first one."""
    q = db.query(FbToken)
    if token_id:
        return q.filter(FbToken.id == token_id).first()
    return q.order_by(FbToken.id.asc()).first()


async def _account_health(
    request: AccountHealthRequest,
    tokens: dict[int, FbToken],
) -> AccountHealthResponse:

    # ad_account_id -> human metadata (name etc.)
    meta_per_token: dict[int, dict[str, dict[str, Any]]] = {}
    meta_results = await asyncio.gather(
        *(_account_meta(tokens[tid]) for tid in tokens),
        return_exceptions=True,
    )
    for tid, m in zip(tokens.keys(), meta_results):
        meta_per_token[tid] = m if isinstance(m, dict) else {}

    sem = asyncio.Semaphore(LAUNCH_CONCURRENCY)

    async def fetch(target: AccountTarget) -> AccountHealth:
        token = tokens.get(target.token_id)
        if not token:
            return AccountHealth(
                token_id=target.token_id,
                account_id=target.account_id,
                has_pixel=False,
                has_page=False,
                error="token not found or disabled",
            )
        async with sem:
            client = FbClient(token.access_token, proxy_url=token.proxy_url)
            try:
                pixels_raw, pages_raw = await asyncio.gather(
                    client.pixels(target.account_id),
                    client.promote_pages(target.account_id),
                )
            except FbApiError as exc:
                return AccountHealth(
                    token_id=target.token_id,
                    account_id=target.account_id,
                    has_pixel=False,
                    has_page=False,
                    error=str(exc),
                )

        pixels = [
            PixelInfo(
                id=str(p.get("id")),
                name=p.get("name"),
                is_unavailable=bool(p.get("is_unavailable")),
                last_fired_time=p.get("last_fired_time"),
            )
            for p in pixels_raw
            if p.get("id")
        ]
        pages = [
            PageInfo(id=str(p.get("id")), name=p.get("name"))
            for p in pages_raw
            if p.get("id")
        ]
        meta = meta_per_token.get(target.token_id, {}).get(target.account_id, {})
        return AccountHealth(
            token_id=target.token_id,
            account_id=target.account_id,
            account_name=meta.get("name"),
            has_pixel=any(not p.is_unavailable for p in pixels),
            has_page=bool(pages),
            pixels=pixels,
            pages=pages,
        )

    accounts = await asyncio.gather(*(fetch(t) for t in request.targets))
    return AccountHealthResponse(accounts=list(accounts))


# ===================================================================
#                             Preview / Execute
# ===================================================================


def _resolve_tokens(db: Session, ids: set[int]) -> dict[int, FbToken]:
    if not ids:
        return {}
    rows = (
        db.query(FbToken)
        .filter(FbToken.id.in_(ids), FbToken.is_disabled.is_(False))
        .all()
    )
    return {t.id: t for t in rows}


def _normalize_acc(account_id: str) -> str:
    return account_id[4:] if account_id.startswith("act_") else account_id


def _build_geo_locations(targeting: dict[str, Any]) -> dict[str, Any]:
    """Convert our flat `geo_locations_picked` list (FB-validated rows)
    into FB's nested `geo_locations` targeting structure.

    Falls back to plain `countries` for legacy templates that predate
    the picker.
    """
    picked = targeting.get("geo_locations_picked") or []
    if picked:
        countries: list[str] = []
        country_groups: list[str] = []
        regions: list[dict[str, str]] = []
        cities: list[dict[str, str]] = []
        zips: list[dict[str, str]] = []
        for row in picked:
            t = row.get("type")
            key = row.get("key")
            if not key:
                continue
            if t == "country":
                countries.append(key)
            elif t == "country_group":
                country_groups.append(key)
            elif t == "region":
                regions.append({"key": key})
            elif t == "city":
                cities.append({"key": key})
            elif t == "zip":
                zips.append({"key": key})
        out: dict[str, Any] = {}
        if countries:
            out["countries"] = countries
        if country_groups:
            out["country_groups"] = country_groups
        if regions:
            out["regions"] = regions
        if cities:
            out["cities"] = cities
        if zips:
            out["zips"] = zips
        if out:
            return out
    return {"countries": targeting.get("countries") or []}


def _targeting_summary(t: dict[str, Any]) -> str:
    parts: list[str] = []
    picked = t.get("geo_locations_picked") or []
    if picked:
        labels: list[str] = []
        for row in picked[:5]:
            label = row.get("name") or row.get("key") or ""
            if label:
                labels.append(label)
        if labels:
            extra = "" if len(picked) <= 5 else f" +{len(picked) - 5}"
            parts.append("/".join(labels) + extra)
    else:
        countries = t.get("countries") or []
        if countries:
            parts.append("/".join(countries[:5]))
    age_min = t.get("age_min", 18)
    age_max = t.get("age_max", 65)
    parts.append(f"{age_min}-{age_max}")
    genders = t.get("genders") or []
    if genders == [1]:
        parts.append("male")
    elif genders == [2]:
        parts.append("female")
    return ", ".join(parts) if parts else "wide"


async def _account_meta(token: FbToken) -> dict[str, dict[str, Any]]:
    """Fetch ad-account metadata so previews / errors include human names."""
    client = FbClient(token.access_token, proxy_url=token.proxy_url)
    try:
        accs = await client.ad_accounts()
    except FbApiError:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for a in accs:
        aid = a.get("account_id") or (a.get("id") or "").replace("act_", "")
        if aid:
            out[aid] = a
    return out


@router.post("/preview", response_model=PreviewResponse)
async def launch_preview(
    request: LaunchRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PreviewResponse:
    """Show what would be created — no FB writes."""
    template = db.get(LaunchTemplate, request.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="template not found")
    if not request.targets:
        raise HTTPException(status_code=400, detail="targets must be non-empty")

    cfg = TemplateConfig.model_validate(template.get_config() or {})
    tokens = _resolve_tokens(db, {t.token_id for t in request.targets})

    # Collect account meta once per token to enrich preview.
    metas = await asyncio.gather(
        *(_account_meta(tok) for tok in tokens.values())
    )
    meta_by_token = dict(zip(tokens.keys(), metas))

    plan: list[PreviewRow] = []
    warnings: list[str] = []

    for target in request.targets:
        tok = tokens.get(target.token_id)
        if not tok:
            warnings.append(f"token #{target.token_id} not found or disabled")
            continue
        norm_acc = _normalize_acc(target.account_id)
        meta = meta_by_token.get(target.token_id, {}).get(norm_acc) or {}
        acc_name = meta.get("name")
        currency = meta.get("currency")

        camp_name = request.campaign_name or f"{template.name} — {acc_name or norm_acc}"
        adset_name = request.adset_name or f"{template.name} adset"

        plan.append(
            PreviewRow(
                token_id=target.token_id,
                account_id=norm_acc,
                account_name=acc_name,
                currency=currency,
                campaign_name=camp_name,
                adset_name=adset_name,
                objective=cfg.campaign.objective,
                daily_budget=cfg.campaign.daily_budget or cfg.adset.daily_budget,
                optimization_goal=cfg.adset.optimization_goal,
                targeting_summary=_targeting_summary(cfg.adset.targeting.model_dump()),
            )
        )

    if cfg.campaign.objective in {"OUTCOME_SALES", "OUTCOME_LEADS"} and not (
        cfg.adset.promoted_object and cfg.adset.promoted_object.pixel_id
    ):
        warnings.append(
            "Sales/Leads objective is selected but no pixel_id is set in the template — "
            "FB may reject the adset."
        )
    if cfg.campaign.status == "ACTIVE":
        warnings.append(
            "Campaign status is ACTIVE — campaigns will start spending immediately. "
            "Double-check before launching."
        )

    return PreviewResponse(plan=plan, warnings=warnings)


def _to_cents(amount: float | None) -> int | None:
    if amount is None:
        return None
    return int(round(float(amount) * 100))


@router.post("/execute", response_model=LaunchResponse)
async def launch_execute(
    request: LaunchRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> LaunchResponse:
    """Create Campaign + AdSet on each target account, in parallel."""
    template = db.get(LaunchTemplate, request.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="template not found")
    if not request.targets:
        raise HTTPException(status_code=400, detail="targets must be non-empty")

    cfg = TemplateConfig.model_validate(template.get_config() or {})
    tokens = _resolve_tokens(db, {t.token_id for t in request.targets})

    # Resolve account names once for nicer campaign names.
    metas = await asyncio.gather(
        *(_account_meta(tok) for tok in tokens.values())
    )
    meta_by_token = dict(zip(tokens.keys(), metas))

    sem = asyncio.Semaphore(LAUNCH_CONCURRENCY)

    async def one(target: AccountTarget) -> LaunchResult:
        async with sem:
            tok = tokens.get(target.token_id)
            if not tok:
                return LaunchResult(
                    token_id=target.token_id,
                    account_id=target.account_id,
                    ok=False,
                    error=f"token #{target.token_id} not found or disabled",
                )
            client = FbClient(tok.access_token, proxy_url=tok.proxy_url)
            norm_acc = _normalize_acc(target.account_id)
            meta = meta_by_token.get(target.token_id, {}).get(norm_acc) or {}
            acc_name = meta.get("name")

            camp_name = request.campaign_name or f"{template.name} — {acc_name or norm_acc}"
            adset_name = request.adset_name or f"{template.name} adset"

            # 1. Create campaign
            try:
                camp = await client.create_campaign(
                    norm_acc,
                    name=camp_name,
                    objective=cfg.campaign.objective,
                    status=cfg.campaign.status,
                    special_ad_categories=cfg.campaign.special_ad_categories,
                    buying_type=cfg.campaign.buying_type,
                    daily_budget_cents=_to_cents(cfg.campaign.daily_budget),
                    lifetime_budget_cents=_to_cents(cfg.campaign.lifetime_budget),
                    bid_strategy=cfg.campaign.bid_strategy,
                )
            except FbApiError as e:
                return LaunchResult(
                    token_id=target.token_id,
                    account_id=norm_acc,
                    ok=False,
                    error=f"campaign create failed: {e}",
                )

            campaign_id = camp.get("id")
            if not campaign_id:
                return LaunchResult(
                    token_id=target.token_id,
                    account_id=norm_acc,
                    ok=False,
                    error=f"FB did not return a campaign id (got {camp!r})",
                )

            # 2. Create adset
            targeting = cfg.adset.targeting.model_dump()
            fb_targeting: dict[str, Any] = {
                "geo_locations": _build_geo_locations(targeting),
                "age_min": targeting.get("age_min", 18),
                "age_max": targeting.get("age_max", 65),
            }
            if targeting.get("genders"):
                fb_targeting["genders"] = targeting["genders"]
            if targeting.get("locales"):
                fb_targeting["locales"] = targeting["locales"]
            if targeting.get("publisher_platforms"):
                fb_targeting["publisher_platforms"] = targeting["publisher_platforms"]

            promoted_object = None
            if cfg.adset.promoted_object:
                po = cfg.adset.promoted_object.model_dump(exclude_none=True)
                if po:
                    promoted_object = po

            try:
                ads = await client.create_adset(
                    norm_acc,
                    name=adset_name,
                    campaign_id=campaign_id,
                    optimization_goal=cfg.adset.optimization_goal,
                    billing_event=cfg.adset.billing_event,
                    status=cfg.adset.status,
                    targeting=fb_targeting,
                    daily_budget_cents=_to_cents(cfg.adset.daily_budget),
                    lifetime_budget_cents=_to_cents(cfg.adset.lifetime_budget),
                    bid_amount_cents=_to_cents(cfg.adset.bid_amount),
                    promoted_object=promoted_object,
                    destination_type=cfg.adset.destination_type,
                    start_time=cfg.adset.start_time,
                    end_time=cfg.adset.end_time,
                    dsa_beneficiary=cfg.adset.dsa_beneficiary,
                    dsa_payor=cfg.adset.dsa_payor,
                )
            except FbApiError as e:
                return LaunchResult(
                    token_id=target.token_id,
                    account_id=norm_acc,
                    ok=False,
                    campaign_id=campaign_id,
                    error=f"adset create failed (campaign was created: {campaign_id}): {e}",
                )

            return LaunchResult(
                token_id=target.token_id,
                account_id=norm_acc,
                ok=True,
                campaign_id=campaign_id,
                adset_id=ads.get("id"),
            )

    results: list[LaunchResult] = await asyncio.gather(
        *(one(t) for t in request.targets)
    )

    # Audit log: one entry per result.
    for r in results:
        db.add(
            BulkActionLog(
                action="launch",
                level="campaign",
                token_id=r.token_id,
                account_id=r.account_id,
                object_id=r.campaign_id or "-",
                result="ok" if r.ok else "error",
                error=r.error,
            )
        )
    db.commit()

    return LaunchResponse(results=results)


# ===================================================================
#                    Execute v2 — full topology + creatives
# ===================================================================


def _pick_creative_index(
    distribution: CreativeDistribution | None,
    flat_index: int,
    total_ads: int,
) -> int | None:
    """Return position into distribution.creative_ids (or None if no ads)."""
    if not distribution or not distribution.creative_ids:
        return None
    n = len(distribution.creative_ids)
    if distribution.mode == "broadcast":
        return 0
    if distribution.mode == "one_per_ad":
        if n != total_ads:
            # Caller validated this already; fall back to round-robin.
            return flat_index % n
        return flat_index
    # round_robin (default)
    return flat_index % n


def _format_name(
    pattern: str | None,
    default: str,
    *,
    tpl: str,
    account: str,
    c: int,
    a: int,
    k: int,
) -> str:
    src = pattern or default
    try:
        return src.format(tpl=tpl, account=account, c=c, a=a, k=k)
    except (KeyError, IndexError):
        return src


@router.post("/execute_v2", response_model=LaunchResponseV2)
async def launch_execute_v2(
    request: LaunchRequestV2,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> LaunchResponseV2:
    """Create N campaigns × M adsets × K ads per (token, account).

    Combines what used to be two separate flows (`/launch/execute` for
    Campaign+AdSet and `/creatives/bulk_create_ads` for Ad creation) into
    a single wizard step. Pure superset — `/launch/execute` and
    `/creatives/bulk_create_ads` continue to work.
    """
    template = db.get(LaunchTemplate, request.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="template not found")
    if not request.targets:
        raise HTTPException(status_code=400, detail="targets must be non-empty")

    cfg = TemplateConfig.model_validate(template.get_config() or {})
    tokens = _resolve_tokens(db, {t.token_id for t in request.targets})

    total_ads_per_account = (
        request.topology.n_campaigns
        * request.topology.n_adsets_per_campaign
        * request.topology.n_ads_per_adset
    )

    # Resolve and validate creatives if user wants Ads.
    creatives_by_id: dict[int, Creative] = {}
    if request.topology.n_ads_per_adset > 0:
        if not request.distribution or not request.distribution.creative_ids:
            raise HTTPException(
                status_code=400,
                detail="distribution.creative_ids is required when n_ads_per_adset > 0",
            )
        ids = list(dict.fromkeys(request.distribution.creative_ids))
        rows = db.query(Creative).filter(Creative.id.in_(ids)).all()
        creatives_by_id = {c.id: c for c in rows}
        missing = [i for i in ids if i not in creatives_by_id]
        if missing:
            raise HTTPException(
                status_code=404, detail=f"creatives not found: {missing}"
            )
        if request.distribution.mode == "one_per_ad" and len(ids) != total_ads_per_account:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"one_per_ad needs exactly {total_ads_per_account} creatives "
                    f"(topology yields {total_ads_per_account} ads per account); "
                    f"got {len(ids)}"
                ),
            )
        for c in creatives_by_id.values():
            if not c.link_url:
                raise HTTPException(
                    status_code=400,
                    detail=f"creative #{c.id} has no link_url; set one before launching",
                )

    # Resolve names for nicer naming defaults.
    metas = await asyncio.gather(*(_account_meta(tok) for tok in tokens.values()))
    meta_by_token = dict(zip(tokens.keys(), metas))

    sem = asyncio.Semaphore(LAUNCH_CONCURRENCY)

    summary = {
        "campaigns_ok": 0,
        "campaigns_failed": 0,
        "adsets_ok": 0,
        "adsets_failed": 0,
        "ads_ok": 0,
        "ads_failed": 0,
    }
    summary_lock = asyncio.Lock()

    async def one(target: AccountTarget) -> LaunchResultV2:
        async with sem:
            tok = tokens.get(target.token_id)
            if not tok:
                return LaunchResultV2(
                    token_id=target.token_id,
                    account_id=target.account_id,
                    ok=False,
                    error=f"token #{target.token_id} not found or disabled",
                )

            client = FbClient(tok.access_token, proxy_url=tok.proxy_url)
            norm_acc = _normalize_acc(target.account_id)
            meta = meta_by_token.get(target.token_id, {}).get(norm_acc) or {}
            account_label = meta.get("name") or f"act_{norm_acc}"

            page_key = f"{target.token_id}:{norm_acc}"
            page_id = request.page_id_per_account.get(page_key)

            # Per-target asset cache: image_hash / video_id keyed by creative.id
            account_assets_cache: dict[int, dict[str, Any]] = {}

            async def ensure_asset(creative: Creative) -> dict[str, Any]:
                # First check the creative's own persisted cache.
                cached_full = creative.get_account_assets()
                key = norm_acc if not norm_acc.startswith("act_") else norm_acc[4:]
                act_key = f"act_{key}"
                got = account_assets_cache.get(creative.id)
                if got:
                    return got
                got = dict(cached_full.get(act_key, {}))
                if creative.media_type == "image" and got.get("image_hash"):
                    account_assets_cache[creative.id] = got
                    return got
                if creative.media_type == "video" and got.get("video_id"):
                    account_assets_cache[creative.id] = got
                    return got

                media_path = settings.uploads_dir / creative.media_filename
                if not media_path.exists():
                    raise FbApiError(
                        code=None,
                        message=f"local media file missing for creative #{creative.id}",
                    )
                content = media_path.read_bytes()
                mime = creative.media_mime or "application/octet-stream"
                fname = creative.media_filename
                if creative.media_type == "image":
                    h = await client.upload_image(
                        norm_acc, filename=fname, content=content, mime=mime
                    )
                    got["image_hash"] = h
                else:
                    vid = await client.upload_video(
                        norm_acc, filename=fname, content=content, mime=mime
                    )
                    got["video_id"] = vid
                account_assets_cache[creative.id] = got
                # Persist to DB so future runs reuse.
                full = creative.get_account_assets()
                full[act_key] = got
                creative.set_account_assets(full)
                return got

            # Build targeting once.
            targeting = cfg.adset.targeting.model_dump()
            fb_targeting: dict[str, Any] = {
                "geo_locations": _build_geo_locations(targeting),
                "age_min": targeting.get("age_min", 18),
                "age_max": targeting.get("age_max", 65),
            }
            if targeting.get("genders"):
                fb_targeting["genders"] = targeting["genders"]
            if targeting.get("locales"):
                fb_targeting["locales"] = targeting["locales"]
            if targeting.get("publisher_platforms"):
                fb_targeting["publisher_platforms"] = targeting["publisher_platforms"]

            promoted_object = None
            if cfg.adset.promoted_object:
                po = cfg.adset.promoted_object.model_dump(exclude_none=True)
                if po:
                    promoted_object = po

            # Per-account pixel override (Sales / Leads / Conversions). Always
            # applied if the user picked one — even when the template had no
            # promoted_object — because objectives that need a pixel will be
            # rejected by FB without it.
            override_pixel = request.pixel_id_per_account.get(page_key)
            if override_pixel:
                if promoted_object is None:
                    promoted_object = {}
                promoted_object["pixel_id"] = override_pixel

            campaigns_out: list[CampaignResultV2] = []
            flat_ad_idx = 0

            for ci in range(1, request.topology.n_campaigns + 1):
                camp_name = _format_name(
                    request.campaign_name_pattern,
                    "{tpl} — {account}" + (f" #{ci}" if request.topology.n_campaigns > 1 else ""),
                    tpl=template.name,
                    account=account_label,
                    c=ci,
                    a=0,
                    k=0,
                )
                try:
                    camp = await client.create_campaign(
                        norm_acc,
                        name=camp_name,
                        objective=cfg.campaign.objective,
                        status=cfg.campaign.status,
                        special_ad_categories=cfg.campaign.special_ad_categories,
                        buying_type=cfg.campaign.buying_type,
                        daily_budget_cents=_to_cents(cfg.campaign.daily_budget),
                        lifetime_budget_cents=_to_cents(cfg.campaign.lifetime_budget),
                        bid_strategy=cfg.campaign.bid_strategy,
                    )
                    campaign_id = str(camp.get("id") or "")
                    if not campaign_id:
                        raise FbApiError(code=None, message="no campaign id returned")
                    async with summary_lock:
                        summary["campaigns_ok"] += 1
                except FbApiError as exc:
                    async with summary_lock:
                        summary["campaigns_failed"] += 1
                    campaigns_out.append(
                        CampaignResultV2(name=camp_name, error=f"campaign create failed: {exc}")
                    )
                    continue

                campaign_result = CampaignResultV2(name=camp_name, campaign_id=campaign_id)
                campaigns_out.append(campaign_result)

                for ai in range(1, request.topology.n_adsets_per_campaign + 1):
                    adset_name = _format_name(
                        request.adset_name_pattern,
                        "{tpl} adset" + (f" #{ai}" if request.topology.n_adsets_per_campaign > 1 else ""),
                        tpl=template.name,
                        account=account_label,
                        c=ci,
                        a=ai,
                        k=0,
                    )
                    try:
                        ads_obj = await client.create_adset(
                            norm_acc,
                            name=adset_name,
                            campaign_id=campaign_id,
                            optimization_goal=cfg.adset.optimization_goal,
                            billing_event=cfg.adset.billing_event,
                            status=cfg.adset.status,
                            targeting=fb_targeting,
                            daily_budget_cents=_to_cents(cfg.adset.daily_budget),
                            lifetime_budget_cents=_to_cents(cfg.adset.lifetime_budget),
                            bid_amount_cents=_to_cents(cfg.adset.bid_amount),
                            promoted_object=promoted_object,
                            destination_type=cfg.adset.destination_type,
                            start_time=cfg.adset.start_time,
                            end_time=cfg.adset.end_time,
                            dsa_beneficiary=cfg.adset.dsa_beneficiary,
                            dsa_payor=cfg.adset.dsa_payor,
                        )
                        adset_id = str(ads_obj.get("id") or "")
                        if not adset_id:
                            raise FbApiError(code=None, message="no adset id returned")
                        async with summary_lock:
                            summary["adsets_ok"] += 1
                    except FbApiError as exc:
                        async with summary_lock:
                            summary["adsets_failed"] += 1
                        # advance flat_ad_idx anyway so creative round-robin stays stable
                        flat_ad_idx += request.topology.n_ads_per_adset
                        campaign_result.adsets.append(
                            AdSetResultV2(name=adset_name, error=f"adset create failed: {exc}")
                        )
                        continue

                    adset_result = AdSetResultV2(name=adset_name, adset_id=adset_id)
                    campaign_result.adsets.append(adset_result)

                    for ki in range(1, request.topology.n_ads_per_adset + 1):
                        cidx = _pick_creative_index(
                            request.distribution, flat_ad_idx, total_ads_per_account
                        )
                        flat_ad_idx += 1
                        if cidx is None:
                            continue
                        creative_local_id = request.distribution.creative_ids[cidx]
                        creative = creatives_by_id.get(creative_local_id)
                        if not creative:
                            adset_result.ads.append(
                                AdResultV2(
                                    name=f"ad #{ki}",
                                    creative_id=creative_local_id,
                                    error="creative missing",
                                )
                            )
                            async with summary_lock:
                                summary["ads_failed"] += 1
                            continue

                        ad_name = _format_name(
                            request.ad_name_pattern,
                            "{tpl} ad" + (f" #{ki}" if request.topology.n_ads_per_adset > 1 else ""),
                            tpl=template.name,
                            account=account_label,
                            c=ci,
                            a=ai,
                            k=ki,
                        )
                        try:
                            asset = await ensure_asset(creative)
                            cr = await client.create_ad_creative(
                                norm_acc,
                                name=creative.name,
                                page_id=page_id or creative.page_id or "",
                                link_url=creative.link_url or "",
                                message=creative.body,
                                headline=creative.title,
                                description=creative.description,
                                cta_type=creative.cta_type,
                                image_hash=asset.get("image_hash"),
                                video_id=asset.get("video_id"),
                                instagram_actor_id=creative.instagram_actor_id,
                            )
                            fb_cr_id = str(cr.get("id") or "")
                            if not fb_cr_id:
                                raise FbApiError(code=None, message="no creative id returned")
                            ad = await client.create_ad(
                                norm_acc,
                                name=ad_name,
                                adset_id=adset_id,
                                creative_id=fb_cr_id,
                                status=request.ad_status,
                            )
                            ad_id = str(ad.get("id") or "")
                            adset_result.ads.append(
                                AdResultV2(
                                    name=ad_name,
                                    creative_id=creative_local_id,
                                    fb_creative_id=fb_cr_id,
                                    ad_id=ad_id or None,
                                )
                            )
                            async with summary_lock:
                                summary["ads_ok"] += 1
                        except FbApiError as exc:
                            adset_result.ads.append(
                                AdResultV2(
                                    name=ad_name,
                                    creative_id=creative_local_id,
                                    error=f"ad create failed: {exc}",
                                )
                            )
                            async with summary_lock:
                                summary["ads_failed"] += 1

            # Persist any new asset cache entries to DB.
            db.commit()

            top_ok = any(c.campaign_id for c in campaigns_out)
            return LaunchResultV2(
                token_id=target.token_id,
                account_id=norm_acc,
                ok=top_ok,
                campaigns=campaigns_out,
            )

    results = await asyncio.gather(*(one(t) for t in request.targets))

    # Audit log
    for r in results:
        for camp in r.campaigns:
            db.add(
                BulkActionLog(
                    action="launch_v2",
                    level="campaign",
                    token_id=r.token_id,
                    account_id=r.account_id,
                    object_id=camp.campaign_id or "-",
                    result="ok" if camp.campaign_id else "error",
                    error=camp.error,
                )
            )
    db.commit()

    return LaunchResponseV2(results=list(results), summary=summary)
