"""Dashboard / insights aggregation across all stored tokens.

Single endpoint: POST /api/dashboard/rows
- accepts a date window (preset or custom) + level (account/campaign/adset/ad)
- iterates every active token x ad account in parallel
- returns a flat list of rows ready for the React grid
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user
from app.models.fb_token import FbToken
from app.models.user import User
from app.services.fb_client import FbApiError, FbClient

logger = logging.getLogger(__name__)

router = APIRouter()


DatePreset = Literal[
    "today",
    "yesterday",
    "this_week_mon_today",
    "last_7d",
    "last_14d",
    "last_30d",
    "last_90d",
    "this_month",
    "last_month",
    "this_quarter",
    "lifetime",
]

Level = Literal["account", "campaign", "adset", "ad"]


class DashboardRequest(BaseModel):
    date_preset: DatePreset | None = "last_7d"
    since: str | None = None  # YYYY-MM-DD; overrides preset
    until: str | None = None
    level: Level = "campaign"
    account_ids: list[str] | None = None  # filter; if None - all visible
    token_ids: list[int] | None = None  # filter; if None - all active


class DashboardRow(BaseModel):
    token_id: int
    token_label: str | None
    account_id: str | None
    account_name: str | None
    campaign_id: str | None = None
    campaign_name: str | None = None
    adset_id: str | None = None
    adset_name: str | None = None
    ad_id: str | None = None
    ad_name: str | None = None

    impressions: int | None = None
    reach: int | None = None
    clicks: int | None = None
    spend: float | None = None
    cpm: float | None = None
    cpc: float | None = None
    ctr: float | None = None
    frequency: float | None = None

    results: int | None = None
    purchases: int | None = None
    purchase_value: float | None = None
    roas: float | None = None
    cost_per_purchase: float | None = None


class DashboardResponse(BaseModel):
    count: int
    rows: list[DashboardRow]
    errors: list[dict] = Field(default_factory=list)


def _to_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


PURCHASE_ACTION_TYPES = {
    "purchase",
    "offsite_conversion.fb_pixel_purchase",
    "omni_purchase",
}


def _extract_purchase(actions: list[dict] | None, values: list[dict] | None) -> tuple[int | None, float | None]:
    """Return (purchase_count, purchase_value).

    FB Insights `actions` and `action_values` are arrays of {action_type, value}.
    We sum across all purchase-like action types and return the maximum count
    and total value found, since FB sometimes double-counts (offsite + omni).
    """
    pc: int | None = None
    pv: float | None = None
    if actions:
        candidates = [
            _to_int(a.get("value"))
            for a in actions
            if (a.get("action_type") or "").lower() in PURCHASE_ACTION_TYPES
        ]
        candidates = [c for c in candidates if c is not None]
        if candidates:
            pc = max(candidates)
    if values:
        candidates_v = [
            _to_float(v.get("value"))
            for v in values
            if (v.get("action_type") or "").lower() in PURCHASE_ACTION_TYPES
        ]
        candidates_v = [c for c in candidates_v if c is not None]
        if candidates_v:
            pv = max(candidates_v)
    return pc, pv


async def _fetch_token_account(
    token: FbToken,
    account_id: str,
    request: DashboardRequest,
) -> tuple[list[DashboardRow], dict | None]:
    client = FbClient(token.access_token, proxy_url=token.proxy_url)
    kwargs: dict[str, Any] = {"level": request.level}
    if request.since and request.until:
        kwargs["since"] = request.since
        kwargs["until"] = request.until
    else:
        kwargs["date_preset"] = request.date_preset or "last_7d"
    try:
        raw = await client.insights(account_id, **kwargs)
    except FbApiError as e:
        return [], {
            "token_id": token.id,
            "token_label": token.label or token.fb_user_name,
            "account_id": account_id,
            "error": str(e),
            "code": e.code,
        }

    rows: list[DashboardRow] = []
    for r in raw:
        actions = r.get("actions") or []
        values = r.get("action_values") or []
        purchases, purchase_value = _extract_purchase(actions, values)
        # "results" in OUTCOME_SALES with purchase optimization == purchases.
        # Generic results column = purchases (since this app is gambling/sales focused).
        results = purchases
        spend = _to_float(r.get("spend"))
        roas = (purchase_value / spend) if (purchase_value and spend) else None
        cpp = (spend / purchases) if (spend and purchases) else None
        rows.append(
            DashboardRow(
                token_id=token.id,
                token_label=token.label or token.fb_user_name,
                account_id=r.get("account_id") or account_id,
                account_name=r.get("account_name"),
                campaign_id=r.get("campaign_id"),
                campaign_name=r.get("campaign_name"),
                adset_id=r.get("adset_id"),
                adset_name=r.get("adset_name"),
                ad_id=r.get("ad_id"),
                ad_name=r.get("ad_name"),
                impressions=_to_int(r.get("impressions")),
                reach=_to_int(r.get("reach")),
                clicks=_to_int(r.get("clicks")),
                spend=spend,
                cpm=_to_float(r.get("cpm")),
                cpc=_to_float(r.get("cpc")),
                ctr=_to_float(r.get("ctr")),
                frequency=_to_float(r.get("frequency")),
                results=results,
                purchases=purchases,
                purchase_value=purchase_value,
                roas=roas,
                cost_per_purchase=cpp,
            )
        )
    return rows, None


async def _list_active_accounts(token: FbToken) -> tuple[list[str], dict | None]:
    """Return (account_ids, error). The error is surfaced to the dashboard
    `errors[]` so users can see *why* a token contributes no rows.
    """
    client = FbClient(token.access_token, proxy_url=token.proxy_url)
    try:
        accs = await client.ad_accounts()
    except FbApiError as e:
        return [], {
            "token_id": token.id,
            "token_label": token.label or token.fb_user_name,
            "account_id": None,
            "error": str(e),
            "code": e.code,
        }
    out: list[str] = []
    for a in accs:
        aid = a.get("account_id") or (a.get("id", "").removeprefix("act_"))
        if aid:
            out.append(aid)
    return out, None


@router.post("/rows", response_model=DashboardResponse)
async def dashboard_rows(
    request: DashboardRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> DashboardResponse:
    """Aggregate insights across selected (token, account) pairs in parallel."""
    q = db.query(FbToken).filter(FbToken.is_disabled.is_(False), FbToken.status == "active")
    if request.token_ids:
        q = q.filter(FbToken.id.in_(request.token_ids))
    tokens = q.all()

    if not tokens:
        return DashboardResponse(count=0, rows=[], errors=[])

    listing_errors: list[dict] = []

    # Resolve account list per token
    if request.account_ids:
        wanted = set(a.removeprefix("act_") for a in request.account_ids)
        per_token: list[tuple[FbToken, list[str]]] = [(t, list(wanted)) for t in tokens]
    else:
        listings = await asyncio.gather(*(_list_active_accounts(t) for t in tokens))
        per_token = []
        for tok, (accs, err) in zip(tokens, listings):
            per_token.append((tok, accs))
            if err:
                listing_errors.append(err)

    # Fan out
    tasks = []
    for token, accounts in per_token:
        for acc_id in accounts:
            tasks.append(_fetch_token_account(token, acc_id, request))

    if not tasks:
        return DashboardResponse(count=0, rows=[], errors=listing_errors)

    results = await asyncio.gather(*tasks)
    rows: list[DashboardRow] = []
    errors: list[dict] = list(listing_errors)
    for r, e in results:
        rows.extend(r)
        if e:
            errors.append(e)

    return DashboardResponse(count=len(rows), rows=rows, errors=errors)
