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
from app.schemas.launch import (
    AccountHealth,
    AccountHealthRequest,
    AccountHealthResponse,
    AccountTarget,
    LaunchRequest,
    LaunchResponse,
    LaunchResult,
    PageInfo,
    PixelInfo,
    PreviewResponse,
    PreviewRow,
    TemplateConfig,
    TemplateCreate,
    TemplateOut,
    TemplateUpdate,
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


def _targeting_summary(t: dict[str, Any]) -> str:
    parts: list[str] = []
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
            # FB expects countries inside geo_locations
            fb_targeting: dict[str, Any] = {
                "geo_locations": {"countries": targeting.get("countries") or []},
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
