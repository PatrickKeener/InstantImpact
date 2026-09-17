from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import get_settings
from app.services.storage import get_layout, resolve_under_root

router = APIRouter(prefix="/api/system", tags=["system"])


async def _redis_ping(url: str) -> bool:
    try:
        import redis.asyncio as redis

        r = redis.from_url(url)
        ok = bool(await r.ping())
        await r.aclose()
        return ok
    except Exception:
        return False


async def _comfy_health(url: str) -> bool:
    from instantimpact_comfy.client import ComfyClient

    return await ComfyClient(url).health()


async def _gpu_holder(url: str) -> str | None:
    try:
        import redis.asyncio as redis

        r = redis.from_url(url, decode_responses=True)
        val = await r.get("instantimpact:gpu")
        await r.aclose()
        return val
    except Exception:
        return None


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

    redis_ok = await _redis_ping(settings.redis_url)
    comfy_healthy = None
    if settings.comfy_enabled and not settings.mock_generation:
        try:
            from instantimpact_common.offline import enforce_strict_offline

            enforce_strict_offline(settings.comfy_url, settings.strict_offline)
            comfy_healthy = await _comfy_health(settings.comfy_url)
        except Exception:
            comfy_healthy = False
    elif settings.comfy_enabled:
        comfy_healthy = await _comfy_health(settings.comfy_url)

    gpu_holder = await _gpu_holder(settings.redis_url) if redis_ok else None

    status = "ok"
    if settings.comfy_enabled and not settings.mock_generation and comfy_healthy is False:
        status = "degraded"
    if not redis_ok and not settings.mock_generation:
        status = "degraded"

    return {
        "status": status,
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
        "auth_required": settings.auth_is_required(),
        "data_dir": str(data),
        "disk_free_gb": free_gb,
        "redis_ok": redis_ok,
        "comfy_enabled": settings.comfy_enabled,
        "comfy_healthy": comfy_healthy,
        "gpu_locked": bool(gpu_holder),
        "gpu_holder": gpu_holder,
        "toolkit_ready": _toolkit_ready(),
    }


def _toolkit_ready() -> bool:
    from instantimpact_common.toolkit import resolve_toolkit_dir

    return resolve_toolkit_dir(get_settings().ai_toolkit_dir or None) is not None


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
        "auth_required": settings.auth_is_required(),
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
async def media(file_path: str):
    """Serve files under data/ only (path traversal safe)."""
    target = resolve_under_root(file_path)
    if target is None:
        raise HTTPException(status_code=400, detail="invalid path")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(target)
