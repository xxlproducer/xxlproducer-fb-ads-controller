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
