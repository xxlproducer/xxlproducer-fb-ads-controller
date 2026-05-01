"""Thin async wrapper around the Facebook Graph API.

Centralises:
- Base URL + version
- Optional per-token proxy
- Common error parsing (token invalid, rate limit, etc.)

We intentionally keep this dependency-light: raw `httpx` rather than the
Facebook SDK, because the SDK changes shape often and we want fine-grained
control over batch / async-batch requests later.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class FbApiError(Exception):
    """Raised when a Graph API call returns a structured error."""

    code: int | None
    message: str
    type: str | None = None
    subcode: int | None = None
    fbtrace_id: str | None = None

    def __str__(self) -> str:  # noqa: D401
        return f"FB error {self.code}/{self.subcode}: {self.message}"


TOKEN_INVALID_PATTERNS = (
    "error validating access token",
    "session has expired",
    "the session has been invalidated",
    "the user has not authorized application",
    "invalid oauth access token",
)


def is_token_invalid(message: str) -> bool:
    msg = (message or "").lower()
    return any(p in msg for p in TOKEN_INVALID_PATTERNS)


class FbClient:
    """Per-token Graph API client."""

    def __init__(self, access_token: str, proxy_url: str | None = None, timeout: float = 30.0):
        self.access_token = access_token
        self.proxy_url = proxy_url
        self.timeout = timeout

    @property
    def base_url(self) -> str:
        return f"https://graph.facebook.com/{settings.fb_api_version}"

    def _client(self) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {"timeout": self.timeout}
        if self.proxy_url:
            kwargs["proxy"] = self.proxy_url
        return httpx.AsyncClient(**kwargs)

    async def _request(
        self, method: str, path: str, *, params: dict | None = None, data: dict | None = None
    ) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        merged_params = dict(params or {})
        merged_params.setdefault("access_token", self.access_token)

        async with self._client() as client:
            try:
                resp = await client.request(method, url, params=merged_params, data=data)
            except httpx.RequestError as exc:
                logger.warning("FB request error %s: %s", url, exc)
                raise FbApiError(code=None, message=f"network error: {exc}") from exc

        try:
            payload = resp.json()
        except Exception:  # noqa: BLE001
            resp.raise_for_status()
            return resp.text

        if isinstance(payload, dict) and payload.get("error"):
            err = payload["error"]
            raise FbApiError(
                code=err.get("code"),
                subcode=err.get("error_subcode"),
                type=err.get("type"),
                message=err.get("message", "unknown FB error"),
                fbtrace_id=err.get("fbtrace_id"),
            )
        return payload

    # ----------------------------------------------------------- common calls

    async def me(self) -> dict[str, Any]:
        return await self._request("GET", "me", params={"fields": "id,name"})

    async def permissions(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "me/permissions")
        return data.get("data", []) if isinstance(data, dict) else []

    async def ad_accounts(self, limit: int = 100) -> list[dict[str, Any]]:
        fields = ",".join(
            [
                "id",
                "account_id",
                "name",
                "account_status",
                "currency",
                "timezone_name",
                "balance",
                "amount_spent",
                "business{id,name}",
            ]
        )
        data = await self._request(
            "GET", "me/adaccounts", params={"fields": fields, "limit": limit}
        )
        return data.get("data", []) if isinstance(data, dict) else []

    # ----------------------------------------------------------- insights / entity listings

    async def _paginate(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Walk Graph API cursor pagination until exhausted."""
        out: list[dict[str, Any]] = []
        next_url: str | None = None
        merged_params: dict[str, Any] | None = dict(params)
        while True:
            if next_url:
                # next URL already has access_token + cursors
                async with self._client() as client:
                    try:
                        resp = await client.get(next_url)
                    except httpx.RequestError as exc:
                        raise FbApiError(code=None, message=f"network error: {exc}") from exc
                    payload = resp.json() if resp.content else {}
                    if isinstance(payload, dict) and payload.get("error"):
                        err = payload["error"]
                        raise FbApiError(
                            code=err.get("code"),
                            subcode=err.get("error_subcode"),
                            type=err.get("type"),
                            message=err.get("message", "unknown FB error"),
                            fbtrace_id=err.get("fbtrace_id"),
                        )
            else:
                payload = await self._request("GET", path, params=merged_params)
                merged_params = None
            if isinstance(payload, dict):
                out.extend(payload.get("data", []) or [])
                paging = payload.get("paging") or {}
                next_url = paging.get("next")
                if not next_url:
                    break
            else:
                break
        return out

    async def insights(
        self,
        account_id: str,
        *,
        level: str = "account",
        date_preset: str | None = None,
        since: str | None = None,
        until: str | None = None,
        fields: list[str] | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Pull /act_{id}/insights with the given window and level.

        `account_id` should be the numeric id (no `act_` prefix is fine, we'll
        normalise). One of `date_preset` or (`since` + `until`) must be set.
        """
        acc = account_id if account_id.startswith("act_") else f"act_{account_id}"
        f = fields or [
            "account_id",
            "account_name",
            "campaign_id",
            "campaign_name",
            "adset_id",
            "adset_name",
            "ad_id",
            "ad_name",
            "impressions",
            "reach",
            "clicks",
            "spend",
            "cpm",
            "cpc",
            "ctr",
            "frequency",
            "actions",
            "action_values",
        ]
        params: dict[str, Any] = {
            "level": level,
            "fields": ",".join(f),
            "limit": limit,
        }
        if since and until:
            params["time_range"] = f'{{"since":"{since}","until":"{until}"}}'
        elif date_preset:
            params["date_preset"] = date_preset
        return await self._paginate(f"{acc}/insights", params)

    async def campaigns(self, account_id: str, limit: int = 500) -> list[dict[str, Any]]:
        acc = account_id if account_id.startswith("act_") else f"act_{account_id}"
        params = {
            "fields": ",".join(
                [
                    "id",
                    "name",
                    "status",
                    "effective_status",
                    "objective",
                    "daily_budget",
                    "lifetime_budget",
                    "buying_type",
                    "created_time",
                    "updated_time",
                    "start_time",
                    "stop_time",
                ]
            ),
            "limit": limit,
        }
        return await self._paginate(f"{acc}/campaigns", params)

    async def adsets(self, account_id: str, limit: int = 500) -> list[dict[str, Any]]:
        acc = account_id if account_id.startswith("act_") else f"act_{account_id}"
        params = {
            "fields": ",".join(
                [
                    "id",
                    "name",
                    "status",
                    "effective_status",
                    "campaign_id",
                    "daily_budget",
                    "lifetime_budget",
                    "billing_event",
                    "optimization_goal",
                    "created_time",
                    "updated_time",
                ]
            ),
            "limit": limit,
        }
        return await self._paginate(f"{acc}/adsets", params)

    async def ads(self, account_id: str, limit: int = 500) -> list[dict[str, Any]]:
        acc = account_id if account_id.startswith("act_") else f"act_{account_id}"
        params = {
            "fields": ",".join(
                [
                    "id",
                    "name",
                    "status",
                    "effective_status",
                    "adset_id",
                    "campaign_id",
                    "created_time",
                    "updated_time",
                ]
            ),
            "limit": limit,
        }
        return await self._paginate(f"{acc}/ads", params)

    # ----------------------------------------------------------- mutations

    async def update_status(self, object_id: str, status: str) -> dict[str, Any]:
        """POST /<object_id>?status=ACTIVE|PAUSED|ARCHIVED.

        Works uniformly for campaigns, adsets, and ads.
        """
        return await self._request("POST", object_id, data={"status": status})

    async def delete_object(self, object_id: str) -> dict[str, Any]:
        """DELETE /<object_id>. Works for campaigns, adsets, and ads."""
        return await self._request("DELETE", object_id)
