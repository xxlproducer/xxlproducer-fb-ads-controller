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

import json
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

    user_msg: str | None = None

    def __str__(self) -> str:  # noqa: D401
        if self.user_msg:
            return f"FB error {self.code}/{self.subcode}: {self.message} — {self.user_msg}"
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
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        data: dict | None = None,
        files: dict | None = None,
        timeout: float | None = None,
    ) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        merged_params = dict(params or {})
        merged_params.setdefault("access_token", self.access_token)

        # Use a longer timeout for uploads
        client_kwargs: dict[str, Any] = {"timeout": timeout or self.timeout}
        if self.proxy_url:
            client_kwargs["proxy"] = self.proxy_url

        async with httpx.AsyncClient(**client_kwargs) as client:
            try:
                resp = await client.request(
                    method, url, params=merged_params, data=data, files=files
                )
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
                user_msg=err.get("error_user_msg"),
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
                            user_msg=err.get("error_user_msg"),
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

    # ----------------------------------------------------------- creation

    async def create_campaign(
        self,
        account_id: str,
        *,
        name: str,
        objective: str,
        status: str = "PAUSED",
        special_ad_categories: list[str] | None = None,
        buying_type: str = "AUCTION",
        daily_budget_cents: int | None = None,
        lifetime_budget_cents: int | None = None,
        bid_strategy: str | None = None,
    ) -> dict[str, Any]:
        """POST /act_<id>/campaigns. Returns the new campaign id payload."""
        acc = account_id if account_id.startswith("act_") else f"act_{account_id}"
        # FB requires special_ad_categories as a JSON array string, even if empty.
        cats = json.dumps(special_ad_categories or [])
        data: dict[str, Any] = {
            "name": name,
            "objective": objective,
            "status": status,
            "special_ad_categories": cats,
            "buying_type": buying_type,
        }
        if daily_budget_cents is not None:
            data["daily_budget"] = daily_budget_cents
        if lifetime_budget_cents is not None:
            data["lifetime_budget"] = lifetime_budget_cents
        if bid_strategy:
            data["bid_strategy"] = bid_strategy
        return await self._request("POST", f"{acc}/campaigns", data=data)

    async def create_adset(
        self,
        account_id: str,
        *,
        name: str,
        campaign_id: str,
        optimization_goal: str,
        billing_event: str = "IMPRESSIONS",
        status: str = "PAUSED",
        targeting: dict[str, Any] | None = None,
        daily_budget_cents: int | None = None,
        lifetime_budget_cents: int | None = None,
        bid_amount_cents: int | None = None,
        promoted_object: dict[str, Any] | None = None,
        destination_type: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        dsa_beneficiary: str | None = None,
        dsa_payor: str | None = None,
    ) -> dict[str, Any]:
        """POST /act_<id>/adsets. Returns the new adset id payload."""
        acc = account_id if account_id.startswith("act_") else f"act_{account_id}"
        data: dict[str, Any] = {
            "name": name,
            "campaign_id": campaign_id,
            "optimization_goal": optimization_goal,
            "billing_event": billing_event,
            "status": status,
        }
        if targeting is not None:
            data["targeting"] = json.dumps(targeting)
        if daily_budget_cents is not None:
            data["daily_budget"] = daily_budget_cents
        if lifetime_budget_cents is not None:
            data["lifetime_budget"] = lifetime_budget_cents
        if bid_amount_cents is not None:
            data["bid_amount"] = bid_amount_cents
        if promoted_object is not None:
            data["promoted_object"] = json.dumps(promoted_object)
        if destination_type:
            data["destination_type"] = destination_type
        if start_time:
            data["start_time"] = start_time
        if end_time:
            data["end_time"] = end_time
        if dsa_beneficiary:
            data["dsa_beneficiary"] = dsa_beneficiary
        if dsa_payor:
            data["dsa_payor"] = dsa_payor
        return await self._request("POST", f"{acc}/adsets", data=data)

    # ----------------------------------------------------------- creatives

    async def upload_image(
        self,
        account_id: str,
        *,
        filename: str,
        content: bytes,
        mime: str = "image/jpeg",
    ) -> str:
        """Upload an image to /act_<id>/adimages and return its hash.

        FB returns `{"images": {"<filename>": {"hash": "...", "url": "..."}}}`
        """
        acc = account_id if account_id.startswith("act_") else f"act_{account_id}"
        files = {"source": (filename, content, mime)}
        payload = await self._request(
            "POST", f"{acc}/adimages", files=files, timeout=120.0
        )
        images = (payload or {}).get("images") or {}
        if not images:
            raise FbApiError(code=None, message="upload_image: no hash returned")
        # FB keys by an arbitrary basename; just take the first.
        first = next(iter(images.values()))
        h = first.get("hash")
        if not h:
            raise FbApiError(code=None, message="upload_image: missing hash field")
        return h

    async def upload_video(
        self,
        account_id: str,
        *,
        filename: str,
        content: bytes,
        mime: str = "video/mp4",
    ) -> str:
        """Upload a video to /act_<id>/advideos and return its id."""
        acc = account_id if account_id.startswith("act_") else f"act_{account_id}"
        files = {"source": (filename, content, mime)}
        payload = await self._request(
            "POST", f"{acc}/advideos", files=files, timeout=300.0
        )
        vid = (payload or {}).get("id")
        if not vid:
            raise FbApiError(code=None, message="upload_video: no id returned")
        return str(vid)

    async def create_ad_creative(
        self,
        account_id: str,
        *,
        name: str,
        page_id: str,
        link_url: str,
        message: str | None = None,
        headline: str | None = None,
        description: str | None = None,
        cta_type: str | None = None,
        image_hash: str | None = None,
        video_id: str | None = None,
        thumbnail_url: str | None = None,
        instagram_actor_id: str | None = None,
    ) -> dict[str, Any]:
        """POST /act_<id>/adcreatives. Returns the new creative payload (id)."""
        acc = account_id if account_id.startswith("act_") else f"act_{account_id}"

        link_data: dict[str, Any] = {"link": link_url}
        if message:
            link_data["message"] = message
        if headline:
            link_data["name"] = headline
        if description:
            link_data["description"] = description
        if cta_type:
            link_data["call_to_action"] = {
                "type": cta_type,
                "value": {"link": link_url},
            }
        if image_hash:
            link_data["image_hash"] = image_hash

        object_story_spec: dict[str, Any] = {"page_id": page_id}

        if video_id:
            video_data: dict[str, Any] = {
                "video_id": video_id,
                "title": headline or name,
                "message": message or "",
                "call_to_action": {
                    "type": cta_type or "LEARN_MORE",
                    "value": {"link": link_url},
                },
            }
            if thumbnail_url:
                video_data["image_url"] = thumbnail_url
            object_story_spec["video_data"] = video_data
        else:
            object_story_spec["link_data"] = link_data

        if instagram_actor_id:
            object_story_spec["instagram_actor_id"] = instagram_actor_id

        data: dict[str, Any] = {
            "name": name,
            "object_story_spec": json.dumps(object_story_spec),
        }
        return await self._request("POST", f"{acc}/adcreatives", data=data)

    async def create_ad(
        self,
        account_id: str,
        *,
        name: str,
        adset_id: str,
        creative_id: str,
        status: str = "PAUSED",
    ) -> dict[str, Any]:
        """POST /act_<id>/ads. Attaches an existing creative to an adset."""
        acc = account_id if account_id.startswith("act_") else f"act_{account_id}"
        data: dict[str, Any] = {
            "name": name,
            "adset_id": adset_id,
            "creative": json.dumps({"creative_id": creative_id}),
            "status": status,
        }
        return await self._request("POST", f"{acc}/ads", data=data)
