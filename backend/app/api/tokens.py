"""CRUD for stored FB tokens + sync endpoint."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user
from app.models.fb_token import FbToken
from app.models.user import User
from app.schemas.token import TokenAddRequest, TokenOut, TokenWithAccounts
from app.services.fb_client import FbApiError, FbClient

router = APIRouter()


@router.get("/", response_model=list[TokenOut])
def list_tokens(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[FbToken]:
    return db.query(FbToken).order_by(FbToken.id.desc()).all()


@router.post("/", response_model=TokenOut)
async def add_token(
    payload: TokenAddRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FbToken:
    # Validate token by hitting /me + /me/permissions
    client = FbClient(payload.access_token, proxy_url=payload.proxy_url)
    try:
        me = await client.me()
        perms = await client.permissions()
    except FbApiError as exc:
        raise HTTPException(status_code=400, detail=f"FB rejected token: {exc.message}") from exc

    granted = sorted(p["permission"] for p in perms if p.get("status") == "granted")

    # Avoid duplicates by FB user id
    fb_user_id = str(me.get("id"))
    existing = db.query(FbToken).filter(FbToken.fb_user_id == fb_user_id).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"token for user {me.get('name')} ({fb_user_id}) already exists",
        )

    token = FbToken(
        fb_user_id=fb_user_id,
        fb_user_name=me.get("name"),
        label=payload.label,
        access_token=payload.access_token,
        proxy_url=payload.proxy_url,
        granted_scopes=",".join(granted),
        status="active",
        last_synced_at=datetime.now(timezone.utc),
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return token


@router.get("/{token_id}", response_model=TokenWithAccounts)
async def get_token(
    token_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    token = db.query(FbToken).filter(FbToken.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="token not found")

    accounts: list = []
    if not token.is_disabled and token.status == "active":
        client = FbClient(token.access_token, proxy_url=token.proxy_url)
        try:
            raw_accounts = await client.ad_accounts()
            for acc in raw_accounts:
                accounts.append(
                    {
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
        except FbApiError as exc:
            token.status = "invalid"
            token.last_error = exc.message
            db.commit()

    return {
        **TokenOut.model_validate(token).model_dump(),
        "accounts": accounts,
    }


@router.post("/{token_id}/sync", response_model=TokenOut)
async def sync_token(
    token_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FbToken:
    token = db.query(FbToken).filter(FbToken.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="token not found")

    client = FbClient(token.access_token, proxy_url=token.proxy_url)
    try:
        me = await client.me()
        perms = await client.permissions()
    except FbApiError as exc:
        token.status = "invalid"
        token.last_error = exc.message
        db.commit()
        return token

    granted = sorted(p["permission"] for p in perms if p.get("status") == "granted")
    token.fb_user_id = str(me.get("id"))
    token.fb_user_name = me.get("name")
    token.granted_scopes = ",".join(granted)
    token.status = "active"
    token.last_error = None
    token.last_synced_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(token)
    return token


@router.delete("/{token_id}", status_code=204)
def delete_token(
    token_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Response:
    token = db.query(FbToken).filter(FbToken.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="token not found")
    db.delete(token)
    db.commit()
    return Response(status_code=204)
