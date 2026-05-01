"""Bulk Actions across FB campaigns / adsets / ads.

Endpoints:
- POST /api/bulk/inventory       — list objects across selected accounts
- POST /api/bulk/update_status   — pause / activate / archive in batch
- POST /api/bulk/delete          — delete in batch (DELETE on each id)

All mutating endpoints fan out in parallel per (token, object) pair, with
a configurable concurrency cap to be polite to FB.

Every individual mutation result is logged to bulk_action_logs so we can
audit / undo later.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user
from app.models.bulk_action_log import BulkActionLog
from app.models.fb_token import FbToken
from app.models.user import User
from app.services.fb_client import FbApiError, FbClient

logger = logging.getLogger(__name__)

router = APIRouter()

Level = Literal["campaign", "adset", "ad"]
Action = Literal["pause", "activate", "archive"]

# Per-token concurrency for FB mutations. FB tolerates ~25 reqs/s per app /
# token; we keep it well below that.
MUTATION_CONCURRENCY = 6


# ===================================================================
#                              Inventory
# ===================================================================


class InventoryRequest(BaseModel):
    level: Level = "campaign"
    token_ids: list[int] | None = None
    account_ids: list[str] | None = None  # without act_ prefix or with — both ok
    statuses: list[str] | None = None  # filter on effective_status; None = no filter


class InventoryRow(BaseModel):
    token_id: int
    token_label: str | None
    account_id: str
    object_id: str
    name: str | None
    status: str | None
    effective_status: str | None
    parent_id: str | None = None  # campaign_id for adset, adset_id for ad
    campaign_id: str | None = None  # always set for ads/adsets, None for campaigns


class InventoryResponse(BaseModel):
    count: int
    rows: list[InventoryRow]
    errors: list[dict] = Field(default_factory=list)


async def _list_acc_ids(token: FbToken) -> tuple[list[str], dict | None]:
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


async def _fetch_inventory_for(
    token: FbToken, account_id: str, level: Level
) -> tuple[list[InventoryRow], dict | None]:
    client = FbClient(token.access_token, proxy_url=token.proxy_url)
    try:
        if level == "campaign":
            raw = await client.campaigns(account_id)
        elif level == "adset":
            raw = await client.adsets(account_id)
        else:
            raw = await client.ads(account_id)
    except FbApiError as e:
        return [], {
            "token_id": token.id,
            "token_label": token.label or token.fb_user_name,
            "account_id": account_id,
            "error": str(e),
            "code": e.code,
        }

    rows: list[InventoryRow] = []
    for r in raw:
        oid = r.get("id")
        if not oid:
            continue
        parent: str | None = None
        camp: str | None = r.get("campaign_id")
        if level == "adset":
            parent = camp
        elif level == "ad":
            parent = r.get("adset_id")
        rows.append(
            InventoryRow(
                token_id=token.id,
                token_label=token.label or token.fb_user_name,
                account_id=account_id,
                object_id=str(oid),
                name=r.get("name"),
                status=r.get("status"),
                effective_status=r.get("effective_status"),
                parent_id=parent,
                campaign_id=camp,
            )
        )
    return rows, None


@router.post("/inventory", response_model=InventoryResponse)
async def bulk_inventory(
    request: InventoryRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> InventoryResponse:
    q = db.query(FbToken).filter(FbToken.is_disabled.is_(False), FbToken.status == "active")
    if request.token_ids:
        q = q.filter(FbToken.id.in_(request.token_ids))
    tokens = q.all()
    if not tokens:
        return InventoryResponse(count=0, rows=[], errors=[])

    listing_errors: list[dict] = []
    if request.account_ids:
        wanted = [a.removeprefix("act_") for a in request.account_ids]
        per_token: list[tuple[FbToken, list[str]]] = [(t, list(wanted)) for t in tokens]
    else:
        listings = await asyncio.gather(*(_list_acc_ids(t) for t in tokens))
        per_token = []
        for tok, (accs, err) in zip(tokens, listings):
            per_token.append((tok, accs))
            if err:
                listing_errors.append(err)

    tasks = []
    for token, accounts in per_token:
        for acc_id in accounts:
            tasks.append(_fetch_inventory_for(token, acc_id, request.level))

    if not tasks:
        return InventoryResponse(count=0, rows=[], errors=listing_errors)

    results = await asyncio.gather(*tasks)
    rows: list[InventoryRow] = []
    errors: list[dict] = list(listing_errors)
    for r, e in results:
        rows.extend(r)
        if e:
            errors.append(e)

    if request.statuses:
        wanted_st = {s.upper() for s in request.statuses}
        rows = [r for r in rows if (r.effective_status or "").upper() in wanted_st]

    return InventoryResponse(count=len(rows), rows=rows, errors=errors)


# ===================================================================
#                              Mutations
# ===================================================================


class TargetRef(BaseModel):
    """Identifies one FB object to mutate, plus which token to use."""

    token_id: int
    object_id: str
    account_id: str | None = None  # for logging only


class UpdateStatusRequest(BaseModel):
    action: Action
    level: Level
    targets: list[TargetRef]


class DeleteRequest(BaseModel):
    level: Level
    targets: list[TargetRef]


class MutationResult(BaseModel):
    object_id: str
    token_id: int
    ok: bool
    error: str | None = None


class MutationResponse(BaseModel):
    total: int
    succeeded: int
    failed: int
    results: list[MutationResult]


_FB_STATUS_MAP: dict[Action, str] = {
    "pause": "PAUSED",
    "activate": "ACTIVE",
    "archive": "ARCHIVED",
}


async def _run_with_concurrency(coros: list, limit: int) -> list:
    """Run coroutines with a concurrency cap, preserving order."""
    sem = asyncio.Semaphore(limit)

    async def gated(coro):
        async with sem:
            return await coro

    return await asyncio.gather(*(gated(c) for c in coros))


def _log(
    db: Session,
    *,
    action: str,
    level: str,
    token_id: int,
    account_id: str | None,
    object_id: str,
    ok: bool,
    error: str | None,
) -> None:
    db.add(
        BulkActionLog(
            action=action,
            level=level,
            token_id=token_id,
            account_id=account_id,
            object_id=object_id,
            result="ok" if ok else "error",
            error=error,
        )
    )


def _resolve_tokens(db: Session, token_ids: set[int]) -> dict[int, FbToken]:
    if not token_ids:
        return {}
    rows = db.query(FbToken).filter(FbToken.id.in_(token_ids)).all()
    return {t.id: t for t in rows}


@router.post("/update_status", response_model=MutationResponse)
async def bulk_update_status(
    request: UpdateStatusRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> MutationResponse:
    if not request.targets:
        raise HTTPException(status_code=400, detail="targets must be non-empty")
    tokens = _resolve_tokens(db, {t.token_id for t in request.targets})
    fb_status = _FB_STATUS_MAP[request.action]

    async def one(target: TargetRef) -> MutationResult:
        tok = tokens.get(target.token_id)
        if not tok:
            return MutationResult(
                object_id=target.object_id, token_id=target.token_id, ok=False,
                error=f"token #{target.token_id} not found or inaccessible",
            )
        client = FbClient(tok.access_token, proxy_url=tok.proxy_url)
        try:
            await client.update_status(target.object_id, fb_status)
            return MutationResult(object_id=target.object_id, token_id=target.token_id, ok=True)
        except FbApiError as e:
            return MutationResult(
                object_id=target.object_id, token_id=target.token_id, ok=False, error=str(e),
            )

    results = await _run_with_concurrency(
        [one(t) for t in request.targets], MUTATION_CONCURRENCY
    )

    for target, res in zip(request.targets, results):
        _log(
            db,
            action=request.action,
            level=request.level,
            token_id=target.token_id,
            account_id=target.account_id,
            object_id=target.object_id,
            ok=res.ok,
            error=res.error,
        )
    db.commit()

    succ = sum(1 for r in results if r.ok)
    return MutationResponse(
        total=len(results), succeeded=succ, failed=len(results) - succ, results=results,
    )


@router.post("/delete", response_model=MutationResponse)
async def bulk_delete(
    request: DeleteRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> MutationResponse:
    if not request.targets:
        raise HTTPException(status_code=400, detail="targets must be non-empty")
    tokens = _resolve_tokens(db, {t.token_id for t in request.targets})

    async def one(target: TargetRef) -> MutationResult:
        tok = tokens.get(target.token_id)
        if not tok:
            return MutationResult(
                object_id=target.object_id, token_id=target.token_id, ok=False,
                error=f"token #{target.token_id} not found or inaccessible",
            )
        client = FbClient(tok.access_token, proxy_url=tok.proxy_url)
        try:
            await client.delete_object(target.object_id)
            return MutationResult(object_id=target.object_id, token_id=target.token_id, ok=True)
        except FbApiError as e:
            return MutationResult(
                object_id=target.object_id, token_id=target.token_id, ok=False, error=str(e),
            )

    results = await _run_with_concurrency(
        [one(t) for t in request.targets], MUTATION_CONCURRENCY
    )

    for target, res in zip(request.targets, results):
        _log(
            db,
            action="delete",
            level=request.level,
            token_id=target.token_id,
            account_id=target.account_id,
            object_id=target.object_id,
            ok=res.ok,
            error=res.error,
        )
    db.commit()

    succ = sum(1 for r in results if r.ok)
    return MutationResponse(
        total=len(results), succeeded=succ, failed=len(results) - succ, results=results,
    )


# ===================================================================
#                              Audit log
# ===================================================================


class LogEntry(BaseModel):
    id: int
    action: str
    level: str
    token_id: int
    account_id: str | None
    object_id: str
    result: str
    error: str | None
    created_at: str


class LogResponse(BaseModel):
    count: int
    entries: list[LogEntry]


@router.get("/log", response_model=LogResponse)
def bulk_log(
    limit: int = 100,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> LogResponse:
    limit = max(1, min(limit, 500))
    rows: list[BulkActionLog] = (
        db.query(BulkActionLog)
        .order_by(BulkActionLog.created_at.desc())
        .limit(limit)
        .all()
    )
    entries = [
        LogEntry(
            id=r.id,
            action=r.action,
            level=r.level,
            token_id=r.token_id,
            account_id=r.account_id,
            object_id=r.object_id,
            result=r.result,
            error=r.error,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in rows
    ]
    return LogResponse(count=len(entries), entries=entries)
