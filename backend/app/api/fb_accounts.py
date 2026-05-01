"""Aggregated view of FB ad accounts across all stored tokens."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user
from app.models.fb_token import FbToken
from app.models.user import User
from app.services.fb_client import FbApiError, FbClient

router = APIRouter()


async def _fetch_for_token(token: FbToken) -> list[dict]:
    if token.is_disabled or token.status != "active":
        return []
    client = FbClient(token.access_token, proxy_url=token.proxy_url)
    try:
        raw = await client.ad_accounts()
    except FbApiError:
        return []
    out = []
    for acc in raw:
        out.append(
            {
                "token_id": token.id,
                "token_label": token.label or token.fb_user_name,
                "fb_user_name": token.fb_user_name,
                "id": acc.get("account_id") or (acc.get("id", "").removeprefix("act_")),
                "name": acc.get("name"),
                "account_status": acc.get("account_status"),
                "currency": acc.get("currency"),
                "timezone_name": acc.get("timezone_name"),
                "balance": acc.get("balance"),
                "amount_spent": acc.get("amount_spent"),
                "business_id": (acc.get("business") or {}).get("id"),
                "business_name": (acc.get("business") or {}).get("name"),
            }
        )
    return out


@router.get("/")
async def list_all_accounts(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    """Fetch ad accounts from every stored, active token concurrently."""
    tokens = db.query(FbToken).filter(FbToken.is_disabled.is_(False)).all()
    results = await asyncio.gather(*(_fetch_for_token(t) for t in tokens))
    flat = [acc for batch in results for acc in batch]
    return {"count": len(flat), "accounts": flat}
