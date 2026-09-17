from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.schemas.jobs import (
    ApprovedSetCreateRequest,
    ApprovedSetExportRequest,
    ApprovedSetOut,
    AssetBulkDeleteRequest,
    AssetBulkDeleteResponse,
    AssetDecisionRequest,
    AssetDeleteResponse,
    AssetOut,
    GpuStatusOut,
    JobOut,
    RegenerateAssetRequest,
    SeedGalleryRequest,
    StillBatchRequest,
)
from app.services import approved as approved_svc
from app.services import jobs as svc

router = APIRouter(prefix="/api", tags=["jobs"])


def _err(e: svc.JobServiceError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/characters/{character_id}/seed-gallery", response_model=JobOut)
async def seed_gallery(
    character_id: str,
    payload: SeedGalleryRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await svc.enqueue_seed_gallery(
            db, character_id, payload, background_tasks=background_tasks
        )
    except svc.JobServiceError as e:
        raise _err(e) from e


@router.post("/characters/{character_id}/still-batch", response_model=JobOut)
async def still_batch(
    character_id: str,
    payload: StillBatchRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await svc.enqueue_still_batch(
            db, character_id, payload, background_tasks=background_tasks
        )
    except svc.JobServiceError as e:
        raise _err(e) from e


@router.get("/jobs", response_model=list[JobOut])
async def list_jobs(character_id: str | None = None, db: AsyncSession = Depends(get_db)):
    return await svc.list_jobs(db, character_id=character_id)


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return svc.job_to_out(await svc.get_job(db, job_id))
    except svc.JobServiceError as e:
        raise _err(e) from e


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
async def cancel_job(job_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await svc.cancel_job(db, job_id)
    except svc.JobServiceError as e:
        raise _err(e) from e


@router.get("/characters/{character_id}/assets", response_model=list[AssetOut])
async def list_assets(
    character_id: str, decision: str | None = None, db: AsyncSession = Depends(get_db)
):
    return await svc.list_assets(db, character_id, decision=decision)


@router.post("/assets/{asset_id}/decision")
async def asset_decision(
    asset_id: str, payload: AssetDecisionRequest, db: AsyncSession = Depends(get_db)
):
    try:
        return await svc.set_asset_decision(
            db, asset_id, payload.decision, score=payload.score, notes=payload.notes
        )
    except svc.JobServiceError as e:
        raise _err(e) from e


@router.delete("/assets/{asset_id}", response_model=AssetDeleteResponse)
async def delete_asset(
    asset_id: str,
    delete_files: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete an asset from the library (DB + optional files under data/)."""
    try:
        return await svc.delete_asset(db, asset_id, delete_files=delete_files)
    except svc.JobServiceError as e:
        raise _err(e) from e


@router.post(
    "/characters/{character_id}/assets/delete",
    response_model=AssetBulkDeleteResponse,
)
async def bulk_delete_assets(
    character_id: str,
    payload: AssetBulkDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Bulk delete assets by id list and/or decision filter (e.g. all rejected)."""
    if not payload.asset_ids and not payload.decision:
        raise HTTPException(
            status_code=400,
            detail="Provide asset_ids and/or decision filter",
        )
    try:
        return await svc.delete_assets_bulk(
            db,
            character_id=character_id,
            asset_ids=payload.asset_ids,
            decision=payload.decision,
            delete_files=payload.delete_files,
        )
    except svc.JobServiceError as e:
        raise _err(e) from e


@router.post(
    "/characters/{character_id}/assets/{asset_id}/regenerate",
    response_model=JobOut,
)
async def regenerate_asset(
    character_id: str,
    asset_id: str,
    background_tasks: BackgroundTasks,
    payload: RegenerateAssetRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    body = payload or RegenerateAssetRequest()
    try:
        return await svc.enqueue_regenerate(
            db,
            character_id,
            asset_id,
            count=body.count,
            background_tasks=background_tasks,
        )
    except svc.JobServiceError as e:
        raise _err(e) from e


@router.get("/characters/{character_id}/approved-sets", response_model=list[ApprovedSetOut])
async def list_approved_sets(character_id: str, db: AsyncSession = Depends(get_db)):
    return await approved_svc.list_sets(db, character_id)


@router.post("/characters/{character_id}/approved-sets", response_model=ApprovedSetOut)
async def create_approved_set(
    character_id: str,
    payload: ApprovedSetCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await approved_svc.create_set(
            db, character_id, title=payload.title, asset_ids=payload.asset_ids
        )
    except svc.JobServiceError as e:
        raise _err(e) from e


@router.get("/approved-sets/{set_id}", response_model=ApprovedSetOut)
async def get_approved_set(set_id: str, db: AsyncSession = Depends(get_db)):
    try:
        aset, items = await approved_svc.get_set(db, set_id)
        return approved_svc._set_to_out(aset, items)
    except svc.JobServiceError as e:
        raise _err(e) from e


@router.post("/approved-sets/{set_id}/export", response_model=ApprovedSetOut)
async def export_approved_set(
    set_id: str,
    payload: ApprovedSetExportRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await approved_svc.export_set(
            db, set_id, confirm_adult_synthetic=payload.confirm_adult_synthetic
        )
    except svc.JobServiceError as e:
        raise _err(e) from e


@router.get("/system/gpu", response_model=GpuStatusOut)
async def gpu_status():
    settings = get_settings()
    comfy_healthy = None
    redis_ok = None
    holder = None
    queue_depth = 0
    try:
        import redis.asyncio as redis

        r = redis.from_url(settings.redis_url, decode_responses=True)
        redis_ok = bool(await r.ping())
        holder = await r.get("instantimpact:gpu")
        for key in ("instantimpact", "arq:queue:instantimpact"):
            n = await r.llen(key)
            if n:
                queue_depth = int(n)
                break
        await r.aclose()
    except Exception:
        redis_ok = False
    if settings.comfy_enabled:
        try:
            from instantimpact_comfy.client import ComfyClient

            comfy_healthy = await ComfyClient(settings.comfy_url).health()
        except Exception:
            comfy_healthy = False
    locked = bool(holder)
    if settings.mock_generation:
        message = "mock generation (no GPU)"
    elif locked:
        message = f"busy ({holder})"
    elif comfy_healthy is False:
        message = "ComfyUI unreachable"
    elif redis_ok is False:
        message = "Redis unreachable"
    elif queue_depth:
        message = f"{queue_depth} job(s) queued — start native GPU worker"
    else:
        message = "idle"
    return GpuStatusOut(
        locked=locked,
        holder_job_id=holder,
        message=message,
        mock_generation=settings.mock_generation,
        comfy_enabled=settings.comfy_enabled,
        comfy_healthy=comfy_healthy,
        redis_ok=redis_ok,
        queue_depth=queue_depth,
    )
