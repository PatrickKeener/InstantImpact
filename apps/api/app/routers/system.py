from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.config import get_settings
from app.services.storage import get_layout

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/health")
async def health():
    settings = get_settings()
    layout = get_layout()
    data = layout.root
    free_gb = None
    try:
        import shutil

        usage = shutil.disk_usage(str(data))
        free_gb = round(usage.free / (1024**3), 2)
    except Exception:
        pass
    return {
        "status": "ok",
        "app": "instantimpact",
        "version": "0.1.0",
        "node": settings.node_name,
        "role": settings.node_role,
        "mvp": {
            "pipeline": "flux",
            "video": settings.enable_video,
            "captions": settings.enable_captions,
            "sdxl": settings.enable_sdxl,
            "external_refs": settings.enable_external_refs,
            "mock_generation": settings.mock_generation,
        },
        "strict_offline": settings.strict_offline,
        "data_dir": str(data),
        "disk_free_gb": free_gb,
    }


@router.get("/topology")
async def topology():
    """Deployment hints for nemesis all-in-one vs split setups."""
    settings = get_settings()
    return {
        "recommended": "all-in-one on nemesis (10.10.101.150) with L40S",
        "node_name": settings.node_name,
        "node_role": settings.node_role,
        "public_base_url": settings.public_base_url,
        "redis_url_configured": bool(settings.redis_url),
        "comfy_url": settings.comfy_url,
        "comfy_enabled": settings.comfy_enabled,
        "mock_generation": settings.mock_generation,
        "auth_required": settings.require_auth_token,
        "hosts": {
            "nemesis": {
                "ip": "10.10.101.150",
                "role": "GPU + recommended control plane (L40S)",
            },
            "chamber": {
                "ip": "10.10.30.184",
                "role": "optional browser client only",
            },
        },
        "docs": "docs/deployment.md",
    }


@router.get("/media/{file_path:path}")
async def media(file_path: str, token: str | None = None):
    """Serve files under data/ only (path traversal safe).

    Optional ?token= for <img> tags when API token auth is enabled (LAN).
    """
    from app.config import get_settings

    settings = get_settings()
    if settings.require_auth_token and settings.api_token:
        # Middleware skips some paths; media is protected here if token required
        # (middleware currently does not exempt media — bearer or query token)
        pass

    layout = get_layout()
    root = layout.root.resolve()
    target = (root / file_path).resolve()
    if not str(target).startswith(str(root)):
        return {"error": "invalid path"}
    if not target.is_file():
        return {"error": "not found"}
    return FileResponse(target)
