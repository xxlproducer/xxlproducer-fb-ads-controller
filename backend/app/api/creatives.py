"""Creative library + bulk Ad creation across many AdSets.

A creative is a reusable spec: media file (image/video) + headline / body /
description / link / CTA / page. We store the media file locally in
`data/uploads/`. When the user wants to launch ads with this creative across
many ad accounts, we:

1. For each unique (token, ad_account_id) target, ensure the media is
   uploaded *to that ad account* (FB requires it) and cache the
   image_hash / video_id in `creatives.account_assets_json`.
2. POST /act_<id>/adcreatives with the resolved object_story_spec.
3. POST /act_<id>/ads attaching the new creative to the target adset.

All FB calls fan out under a small semaphore to avoid rate-limit issues.
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import secrets
from pathlib import Path
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.deps import get_current_user
from app.models.bulk_action_log import BulkActionLog
from app.models.creative import Creative
from app.models.fb_token import FbToken
from app.models.user import User
from app.schemas.creative import (
    AdResult,
    BulkCreateAdsRequest,
    BulkCreateAdsResponse,
    CreativeOut,
    CreativeUpdate,
)
from app.services.fb_client import FbApiError, FbClient

logger = logging.getLogger(__name__)

router = APIRouter()

# FB tolerates ~25 reqs/s per token; keep mutations well below.
AD_CREATE_CONCURRENCY = 3

ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
ALLOWED_VIDEO_MIMES = {"video/mp4", "video/quicktime", "video/x-m4v"}
MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB


def _to_out(c: Creative) -> CreativeOut:
    return CreativeOut(
        id=c.id,
        name=c.name,
        media_type=c.media_type,
        media_filename=c.media_filename,
        media_mime=c.media_mime,
        thumbnail_filename=c.thumbnail_filename,
        title=c.title,
        body=c.body,
        description=c.description,
        link_url=c.link_url,
        cta_type=c.cta_type,
        page_id=c.page_id,
        instagram_actor_id=c.instagram_actor_id,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def _save_upload(file: UploadFile, allowed_mimes: set[str]) -> tuple[str, str, int]:
    """Save UploadFile to settings.uploads_dir. Returns (filename, mime, size)."""
    raw = file.file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"file too large (>{MAX_UPLOAD_BYTES} bytes)")

    mime = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
    if allowed_mimes and mime not in allowed_mimes:
        raise HTTPException(status_code=415, detail=f"unsupported media type: {mime}")

    ext = Path(file.filename or "").suffix or mimetypes.guess_extension(mime) or ""
    fname = f"{secrets.token_hex(12)}{ext}"
    out_path = settings.uploads_dir / fname
    out_path.write_bytes(raw)
    return fname, mime, len(raw)


# ===================================================================
#                            Creatives CRUD
# ===================================================================


@router.get("", response_model=list[CreativeOut])
def list_creatives(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[CreativeOut]:
    rows = db.query(Creative).order_by(Creative.id.desc()).all()
    return [_to_out(c) for c in rows]


@router.post("", response_model=CreativeOut, status_code=201)
def create_creative(
    name: str = Form(...),
    media: UploadFile = File(...),
    title: str | None = Form(None),
    body: str | None = Form(None),
    description: str | None = Form(None),
    link_url: str | None = Form(None),
    cta_type: str | None = Form("LEARN_MORE"),
    page_id: str | None = Form(None),
    instagram_actor_id: str | None = Form(None),
    thumbnail: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> CreativeOut:
    media_mime = media.content_type or ""
    if media_mime in ALLOWED_VIDEO_MIMES:
        media_type = "video"
        allowed = ALLOWED_VIDEO_MIMES
    else:
        media_type = "image"
        allowed = ALLOWED_IMAGE_MIMES

    fname, mime, _size = _save_upload(media, allowed)

    thumb_fname: str | None = None
    if thumbnail is not None and thumbnail.filename:
        thumb_fname, _, _ = _save_upload(thumbnail, ALLOWED_IMAGE_MIMES)

    c = Creative(
        name=name,
        media_type=media_type,
        media_filename=fname,
        media_mime=mime,
        thumbnail_filename=thumb_fname,
        title=title,
        body=body,
        description=description,
        link_url=link_url,
        cta_type=cta_type,
        page_id=page_id,
        instagram_actor_id=instagram_actor_id,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return _to_out(c)


@router.get("/{creative_id}", response_model=CreativeOut)
def get_creative(
    creative_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> CreativeOut:
    c = db.get(Creative, creative_id)
    if not c:
        raise HTTPException(status_code=404, detail="creative not found")
    return _to_out(c)


@router.patch("/{creative_id}", response_model=CreativeOut)
def update_creative(
    creative_id: int,
    payload: CreativeUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> CreativeOut:
    c = db.get(Creative, creative_id)
    if not c:
        raise HTTPException(status_code=404, detail="creative not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return _to_out(c)


@router.delete("/{creative_id}")
def delete_creative(
    creative_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict[str, bool]:
    c = db.get(Creative, creative_id)
    if c:
        # best-effort delete on disk
        for fname in (c.media_filename, c.thumbnail_filename):
            if not fname:
                continue
            p = settings.uploads_dir / fname
            try:
                if p.exists():
                    p.unlink()
            except OSError:
                logger.warning("could not unlink %s", p)
        db.delete(c)
        db.commit()
    return {"ok": True}


@router.get("/{creative_id}/media")
def serve_media(
    creative_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    c = db.get(Creative, creative_id)
    if not c:
        raise HTTPException(status_code=404, detail="creative not found")
    p = settings.uploads_dir / c.media_filename
    if not p.exists():
        raise HTTPException(status_code=404, detail="media file missing")
    return FileResponse(str(p), media_type=c.media_mime or "application/octet-stream")


# ===================================================================
#                       Bulk Create Ads
# ===================================================================


def _normalize_acc(account_id: str) -> str:
    return account_id[4:] if account_id.startswith("act_") else account_id


def _act_key(account_id: str) -> str:
    """Stable key used to cache per-account uploaded asset hashes/ids."""
    return f"act_{_normalize_acc(account_id)}"


@router.post("/bulk_create_ads", response_model=BulkCreateAdsResponse)
async def bulk_create_ads(
    payload: BulkCreateAdsRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> BulkCreateAdsResponse:
    creative = db.get(Creative, payload.creative_id)
    if not creative:
        raise HTTPException(status_code=404, detail="creative not found")

    if not payload.targets:
        return BulkCreateAdsResponse(total=0, succeeded=0, failed=0, results=[])

    if not creative.page_id:
        raise HTTPException(
            status_code=400,
            detail="creative.page_id is required to create FB ads (set it on the creative)",
        )
    if not creative.link_url:
        raise HTTPException(
            status_code=400,
            detail="creative.link_url is required to create FB ads",
        )

    token_ids = {t.token_id for t in payload.targets}
    rows = (
        db.query(FbToken)
        .filter(FbToken.id.in_(token_ids), FbToken.is_disabled.is_(False))
        .all()
    )
    tokens_by_id = {t.id: t for t in rows}

    media_path = settings.uploads_dir / creative.media_filename
    if not media_path.exists():
        raise HTTPException(status_code=410, detail="creative media file missing on disk")
    media_bytes = media_path.read_bytes()
    media_mime = creative.media_mime or "application/octet-stream"
    media_filename = os.path.basename(creative.media_filename)

    sem = asyncio.Semaphore(AD_CREATE_CONCURRENCY)

    # Cache of per-account uploads done in *this* run (avoids re-uploading
    # when the same account appears in multiple targets within one batch).
    cached_assets: dict[str, dict[str, Any]] = dict(creative.get_account_assets())

    async def _ensure_asset(client: FbClient, account_id: str) -> dict[str, Any]:
        key = _act_key(account_id)
        existing = cached_assets.get(key) or {}
        if creative.media_type == "image" and existing.get("image_hash"):
            return existing
        if creative.media_type == "video" and existing.get("video_id"):
            return existing
        if creative.media_type == "image":
            h = await client.upload_image(
                account_id, filename=media_filename, content=media_bytes, mime=media_mime
            )
            existing["image_hash"] = h
        else:
            v = await client.upload_video(
                account_id, filename=media_filename, content=media_bytes, mime=media_mime
            )
            existing["video_id"] = v
        cached_assets[key] = existing
        return existing

    async def _create_one(target_idx: int) -> AdResult:
        target = payload.targets[target_idx]
        token = tokens_by_id.get(target.token_id)
        if not token:
            return AdResult(
                token_id=target.token_id,
                ad_account_id=target.ad_account_id,
                adset_id=target.adset_id,
                success=False,
                error="token not found or disabled",
            )

        async with sem:
            client = FbClient(access_token=token.access_token, proxy_url=token.proxy_url)
            try:
                asset = await _ensure_asset(client, target.ad_account_id)
                creative_payload = await client.create_ad_creative(
                    target.ad_account_id,
                    name=creative.name,
                    page_id=creative.page_id or "",
                    link_url=creative.link_url or "",
                    message=creative.body,
                    headline=creative.title,
                    description=creative.description,
                    cta_type=creative.cta_type,
                    image_hash=asset.get("image_hash"),
                    video_id=asset.get("video_id"),
                    instagram_actor_id=creative.instagram_actor_id,
                )
                fb_creative_id = str(creative_payload.get("id") or "")
                if not fb_creative_id:
                    raise FbApiError(code=None, message="no creative id returned")

                ad_name = target.ad_name or creative.name
                ad_payload = await client.create_ad(
                    target.ad_account_id,
                    name=ad_name,
                    adset_id=target.adset_id,
                    creative_id=fb_creative_id,
                    status=payload.status,
                )
                ad_id = str(ad_payload.get("id") or "")
                return AdResult(
                    token_id=target.token_id,
                    ad_account_id=target.ad_account_id,
                    adset_id=target.adset_id,
                    success=bool(ad_id),
                    ad_id=ad_id or None,
                    creative_id_fb=fb_creative_id,
                    image_hash=asset.get("image_hash"),
                    video_id=asset.get("video_id"),
                )
            except FbApiError as exc:
                return AdResult(
                    token_id=target.token_id,
                    ad_account_id=target.ad_account_id,
                    adset_id=target.adset_id,
                    success=False,
                    error=str(exc),
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("unexpected error creating ad")
                return AdResult(
                    token_id=target.token_id,
                    ad_account_id=target.ad_account_id,
                    adset_id=target.adset_id,
                    success=False,
                    error=f"unexpected: {exc}",
                )

    results = await asyncio.gather(
        *(_create_one(i) for i in range(len(payload.targets)))
    )

    # Persist any newly-acquired per-account assets
    creative.set_account_assets(cached_assets)
    db.add(creative)

    # Audit log
    for r in results:
        log = BulkActionLog(
            action="create_ad",
            level="ad",
            token_id=r.token_id,
            account_id=_normalize_acc(r.ad_account_id),
            object_id=r.ad_id or "",
            result="ok" if r.success else "error",
            error=r.error,
        )
        db.add(log)

    db.commit()

    succeeded = sum(1 for r in results if r.success)
    return BulkCreateAdsResponse(
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        results=results,
    )
