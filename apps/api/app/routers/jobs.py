from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.schemas.jobs import (
    AssetBulkDeleteRequest,
    AssetBulkDeleteResponse,
    AssetDecisionRequest,
    AssetDeleteResponse,
    AssetOut,
    GpuStatusOut,
    JobOut,
    SeedGalleryRequest,
    StillBatchRequest,
)
from app.services import jobs as svc

router = APIRouter(prefix="/api", tags=["jobs"])


def _err(e: svc.JobServiceError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/characters/{character_id}/seed-gallery", response_model=JobOut)
async def seed_gallery(
    character_id: str, payload: SeedGalleryRequest, db: AsyncSession = Depends(get_db)
):
    try:
        return await svc.enqueue_seed_gallery(db, character_id, payload)
    except svc.JobServiceError as e:
        raise _err(e) from e


@router.post("/characters/{character_id}/still-batch", response_model=JobOut)
async def still_batch(
    character_id: str, payload: StillBatchRequest, db: AsyncSession = Depends(get_db)
):
    try:
        return await svc.enqueue_still_batch(db, character_id, payload)
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


@router.get("/system/gpu", response_model=GpuStatusOut)
async def gpu_status():
    settings = get_settings()
    comfy_healthy = None
    if settings.comfy_enabled:
        from instantimpact_comfy.client import ComfyClient

        client = ComfyClient(settings.comfy_url)
        comfy_healthy = await client.health()
    return GpuStatusOut(
        locked=False,
        message="idle (mock)" if settings.mock_generation else "idle",
        mock_generation=settings.mock_generation,
        comfy_enabled=settings.comfy_enabled,
        comfy_healthy=comfy_healthy,
    )
