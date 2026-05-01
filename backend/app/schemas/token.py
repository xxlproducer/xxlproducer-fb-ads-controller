"""FB token-related request/response schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TokenAddRequest(BaseModel):
    access_token: str = Field(min_length=20)
    label: str | None = None
    proxy_url: str | None = None


class TokenOut(BaseModel):
    id: int
    fb_user_id: str | None
    fb_user_name: str | None
    label: str | None
    granted_scopes: str | None
    status: str
    last_error: str | None
    proxy_url: str | None
    is_disabled: bool
    created_at: datetime
    last_synced_at: datetime | None
    # We never expose the raw token in list responses

    class Config:
        from_attributes = True


class FbAccountSummary(BaseModel):
    """Single ad account associated with a token."""

    id: str
    name: str | None
    account_status: int | None
    currency: str | None
    timezone_name: str | None
    balance: str | None
    amount_spent: str | None
    business_id: str | None = None
    business_name: str | None = None


class TokenWithAccounts(TokenOut):
    accounts: list[FbAccountSummary] = []
