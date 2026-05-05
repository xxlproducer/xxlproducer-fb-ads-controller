"""FastAPI entrypoint for the FB Ads Controller backend.

Serves the JSON API under /api/* and the built React frontend at /.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api import auth, bulk, dashboard, fb_accounts, health, launch, tokens
from app.core.config import settings
from app.db.base import init_db

logger = logging.getLogger("fb_ads_controller")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="FB Ads Controller", version="0.1.0")

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="fbac_session",
    max_age=60 * 60 * 24 * 7,
    same_site="lax",
    https_only=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    logger.info("DB initialized at %s", settings.db_path)


# JSON API routers
app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api/auth")
app.include_router(tokens.router, prefix="/api/tokens")
app.include_router(fb_accounts.router, prefix="/api/fb-accounts")
app.include_router(dashboard.router, prefix="/api/dashboard")
app.include_router(bulk.router, prefix="/api/bulk")
app.include_router(launch.router, prefix="/api/launch")


# Static frontend (Vite build) — served when present
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        # Serve favicon and other root files explicitly
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        index = FRONTEND_DIST / "index.html"
        if index.exists():
            return FileResponse(index)
        return JSONResponse({"detail": "frontend not built"}, status_code=503)
else:
    @app.get("/")
    def root_no_frontend():
        return JSONResponse(
            {
                "detail": "frontend not built yet — run `npm run build` in the frontend folder, "
                "or use `npm run dev` for hot reload during development",
                "api_docs": "/docs",
            }
        )
