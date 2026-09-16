from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Ensure packages are importable when running from repo root
_REPO = Path(__file__).resolve().parents[3]
for p in (
    _REPO / "packages" / "common",
    _REPO / "packages" / "comfy_client",
    _REPO / "packages" / "prompt_engine",
    _REPO / "apps" / "api",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from app.config import get_settings
from app.db.session import init_db
from app.routers import characters, jobs, system
from app.services.storage import get_layout

log = logging.getLogger("instantimpact.api")


class ApiTokenMiddleware(BaseHTTPMiddleware):
    """Optional bearer/token gate when LAN-exposed (adult library)."""

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if not settings.auth_is_required():
            return await call_next(request)

        path = request.url.path
        # Allow bare health / docs without token
        if path in ("/", "/api/system/health", "/api/system/topology", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)

        auth = request.headers.get("authorization") or ""
        token = request.headers.get("x-api-token") or ""
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
        # Query token for media <img> tags
        if not token:
            token = request.query_params.get("token") or ""
        if token != settings.api_token:
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    get_layout()  # bootstrap data dirs
    await init_db()
    if settings.bind_is_public() and not settings.api_token:
        log.warning(
            "LAN bind (%s) without INSTANTIMPACT_API_TOKEN — adult library is unauthenticated",
            settings.host,
        )
    if settings.strict_offline:
        log.info("STRICT_OFFLINE enabled — non-loopback HTTP is blocked")
    from app.services.job_events import start_job_event_consumer, stop_job_event_consumer

    start_job_event_consumer()
    try:
        yield
    finally:
        await stop_job_event_consumer()


def create_app() -> FastAPI:
    """Factory so tests can rebuild the app after env/settings changes."""
    application = FastAPI(
        title="InstantImpact",
        description="Local AI Persona Content Studio",
        version="0.1.0",
        lifespan=lifespan,
    )

    settings = get_settings()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(ApiTokenMiddleware)

    application.include_router(system.router)
    application.include_router(characters.router)
    application.include_router(jobs.router)

    @application.get("/")
    async def root():
        s = get_settings()
        return {
            "app": "InstantImpact",
            "node": s.node_name,
            "role": s.node_role,
            "docs": "/docs",
            "health": "/api/system/health",
            "topology": "/api/system/topology",
        }

    return application


app = create_app()
