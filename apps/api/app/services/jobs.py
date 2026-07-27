from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db.models import Asset, ContentBrief, Job, JobItem
from app.schemas.jobs import SeedGalleryRequest, StillBatchRequest
from app.services import characters as char_svc
from app.services.storage import get_layout, relative_to_data, write_json
from instantimpact_common.enums import CharacterStatus, JobItemStatus, JobStatus, JobType
from instantimpact_common.safety import validate_for_enqueue
from instantimpact_common.schemas import BriefItem, JobRequestSnapshot, StillUnitRequest
from instantimpact_prompts.render_flux import render_flux_prompts


class JobServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def job_to_out(job: Job) -> dict:
    return {
        "id": job.id,
        "type": job.type,
        "status": job.status,
        "character_id": job.character_id,
        "character_version_id": job.character_version_id,
        "brief_id": job.brief_id,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "cancel_requested": job.cancel_requested,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "items": [
            {
                "id": i.id,
                "item_index": i.item_index,
                "status": i.status,
                "asset_id": i.asset_id,
                "error_message": i.error_message,
                "consistency_score": i.consistency_score,
                "request": i.request_json or {},
            }
            for i in sorted(job.items, key=lambda x: x.item_index)
        ],
    }


async def get_job(db: AsyncSession, job_id: str) -> Job:
    q = await db.execute(
        select(Job).options(selectinload(Job.items)).where(Job.id == job_id)
    )
    job = q.scalar_one_or_none()
    if not job:
        raise JobServiceError("Job not found", 404)
    return job


def _expand_brief_items(items: list[BriefItem] | list[dict]) -> list[StillUnitRequest]:
    units: list[StillUnitRequest] = []
    idx = 0
    for raw in items:
        item = BriefItem.model_validate(raw) if isinstance(raw, dict) else raw
        if item.type != "still":
            raise JobServiceError(
                f"Item type '{item.type}' is not enabled in MVP (video deferred)"
            )
        for _ in range(item.count):
            units.append(
                StillUnitRequest(
                    item_index=idx,
                    theme=item.theme,
                    outfit_hint=item.outfit_hint,
                    pose_hint=item.pose_hint,
                    location_hint=item.location_hint,
                    extra_prompt=item.extra_prompt,
                )
            )
            idx += 1
    if not units:
        raise JobServiceError("Brief produced zero still units")
    if len(units) > 100:
        raise JobServiceError("Max 100 stills per batch in MVP")
    return units


def _version_for_generation(c) -> Any:
    """Production stills use locked version when ready; else working version."""
    if c.status == CharacterStatus.READY and c.locked_version_id:
        v = next((x for x in c.versions if x.id == c.locked_version_id), None)
        if v:
            return v
    return char_svc._working_version(c)


async def _enqueue(
    db: AsyncSession,
    *,
    job_type: str,
    character_id: str,
    units: list[StillUnitRequest],
    brief_id: str | None = None,
    aspect_ratio: str = "4:5",
    seed_policy: str = "random",
) -> Job:
    settings = get_settings()
    c = await char_svc.get_character(db, character_id)
    version = _version_for_generation(c)
    if not version:
        raise JobServiceError("Character has no version")

    texts = []
    for u in units:
        texts.extend(
            filter(
                None,
                [u.theme, u.outfit_hint, u.pose_hint, u.location_hint, u.extra_prompt],
            )
        )
    safety = validate_for_enqueue(
        job_type=job_type,
        character_status=c.status,
        synthetic_confirmed=c.synthetic_confirmed,
        age_appearance_min=c.age_appearance_min,
        not_real_person_attested=c.not_real_person_attested,
        texts=texts,
        video_enabled=settings.enable_video,
    )
    if not safety.ok:
        raise JobServiceError("; ".join(safety.reasons))

    # Assign seeds
    base_seed = random.randint(1, 2**31 - 1)
    for i, u in enumerate(units):
        u.aspect_ratio = aspect_ratio
        if seed_policy == "fixed_base":
            u.seed = base_seed + i
        else:
            u.seed = random.randint(1, 2**31 - 1)

    job_id = str(uuid.uuid4())
    layout = get_layout()
    job_dir = layout.job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    snapshot = JobRequestSnapshot(
        job_id=job_id,
        type=job_type,
        character_id=c.id,
        character_version_id=version.id,
        locked_version_id=c.locked_version_id,
        pipeline=c.preferred_pipeline,
        trigger_word=version.trigger_word,
        lora_path=version.lora_path,
        ref_pack_path=version.ref_pack_path,
        prompt_contract=version.prompt_contract_json or {},
        pipeline_params=version.pipeline_params_json or {},
        boundaries=version.boundaries_json or {},
        appearance=version.appearance_json or {},
        items=units,
        resume_on_item_failure=True,
        mock=settings.mock_generation or not settings.comfy_enabled,
        meta={"aspect_ratio": aspect_ratio, "seed_policy": seed_policy},
    )
    request_path = layout.job_request_path(job_id)
    write_json(request_path, snapshot.model_dump())

    job = Job(
        id=job_id,
        type=job_type,
        status=JobStatus.QUEUED,
        character_id=c.id,
        character_version_id=version.id,
        brief_id=brief_id,
        request_json=snapshot.model_dump(),
        request_path=str(request_path),
        resume_on_item_failure=True,
    )
    db.add(job)
    await db.flush()

    for u in units:
        db.add(
            JobItem(
                job_id=job.id,
                item_index=u.item_index,
                status=JobItemStatus.PENDING,
                request_json=u.model_dump(),
            )
        )

    await db.commit()
    job = await get_job(db, job.id)

    # Best-effort Redis enqueue; fall back to in-process mock runner
    try:
        await _try_arq_enqueue(job.id, str(request_path), job_type)
    except Exception:
        # Synchronous mock completion when Redis/worker unavailable
        if snapshot.mock:
            await run_mock_job(db, job.id)

    return await get_job(db, job.id)


async def _try_arq_enqueue(job_id: str, request_path: str, job_type: str) -> None:
    settings = get_settings()
    try:
        from arq import create_pool
        from arq.connections import RedisSettings
    except ImportError as e:
        raise RuntimeError("arq not installed") from e

    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await redis.enqueue_job(
            "run_generation_job",
            job_id,
            request_path,
            job_type,
            _queue_name="instantimpact",
        )
    finally:
        await redis.close()


async def enqueue_seed_gallery(
    db: AsyncSession, character_id: str, payload: SeedGalleryRequest
) -> dict:
    themes = payload.themes or ["portrait"]
    units: list[StillUnitRequest] = []
    for i in range(payload.count):
        units.append(
            StillUnitRequest(
                item_index=i,
                theme=themes[i % len(themes)],
                aspect_ratio=payload.aspect_ratio,
            )
        )
    job = await _enqueue(
        db,
        job_type=JobType.SEED_GALLERY,
        character_id=character_id,
        units=units,
        aspect_ratio=payload.aspect_ratio,
    )
    return job_to_out(job)


async def enqueue_still_batch(
    db: AsyncSession, character_id: str, payload: StillBatchRequest
) -> dict:
    units = _expand_brief_items(payload.items)
    brief_id = None
    if payload.title:
        brief = ContentBrief(
            character_id=character_id,
            title=payload.title,
            status="generating",
            items_json=[i.model_dump() for i in payload.items],
            aspect_ratio=payload.aspect_ratio,
            seed_policy=payload.seed_policy,
        )
        db.add(brief)
        await db.flush()
        brief_id = brief.id
    job = await _enqueue(
        db,
        job_type=JobType.STILL_BATCH,
        character_id=character_id,
        units=units,
        brief_id=brief_id,
        aspect_ratio=payload.aspect_ratio,
        seed_policy=payload.seed_policy,
    )
    return job_to_out(job)


async def cancel_job(db: AsyncSession, job_id: str) -> dict:
    job = await get_job(db, job_id)
    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        return job_to_out(job)
    job.cancel_requested = True
    settings = get_settings()
    try:
        import redis.asyncio as redis

        r = redis.from_url(settings.redis_url)
        await r.set(f"instantimpact:cancel:{job_id}", "1")
        await r.publish("instantimpact:cancel", job_id)
        await r.aclose()
    except Exception:
        pass
    await db.commit()
    return job_to_out(await get_job(db, job_id))


async def list_jobs(db: AsyncSession, character_id: str | None = None, limit: int = 50) -> list[dict]:
    q = select(Job).options(selectinload(Job.items)).order_by(Job.created_at.desc()).limit(limit)
    if character_id:
        q = q.where(Job.character_id == character_id)
    rows = (await db.execute(q)).scalars().all()
    return [job_to_out(j) for j in rows]


async def list_assets(db: AsyncSession, character_id: str, decision: str | None = None) -> list[dict]:
    q = select(Asset).where(Asset.character_id == character_id).order_by(Asset.created_at.desc())
    if decision:
        q = q.where(Asset.decision == decision)
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": a.id,
            "character_id": a.character_id,
            "character_version_id": a.character_version_id,
            "job_id": a.job_id,
            "kind": a.kind,
            "path": a.path,
            "thumb_path": a.thumb_path,
            "width": a.width,
            "height": a.height,
            "seed": a.seed,
            "prompt_positive": a.prompt_positive,
            "decision": a.decision,
            "consistency_score": a.consistency_score,
            "meta": a.meta_json or {},
            "created_at": a.created_at,
        }
        for a in rows
    ]


async def set_asset_decision(
    db: AsyncSession, asset_id: str, decision: str, score: int | None = None, notes: str | None = None
) -> dict:
    q = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = q.scalar_one_or_none()
    if not asset:
        raise JobServiceError("Asset not found", 404)
    if decision not in ("pending", "approved", "rejected"):
        raise JobServiceError("Invalid decision")
    asset.decision = decision
    if score is not None or notes:
        from app.db.models import AssetRating

        db.add(
            AssetRating(
                asset_id=asset.id,
                score=score or 3,
                notes=notes,
            )
        )
    await db.commit()
    return {
        "id": asset.id,
        "decision": asset.decision,
        "character_id": asset.character_id,
    }


async def run_mock_job(db: AsyncSession, job_id: str) -> None:
    """In-process mock generator when worker/Comfy unavailable — produces placeholder stills."""
    from PIL import Image, ImageDraw, ImageFont

    from instantimpact_common.safety_lists import SYNTHETIC_DISCLOSURE_DEFAULT

    job = await get_job(db, job_id)
    if job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
        return

    job.status = JobStatus.RUNNING
    job.started_at = datetime.now(timezone.utc)
    await db.commit()

    layout = get_layout()
    settings = get_settings()
    snapshot = job.request_json or {}
    character_id = job.character_id or ""
    version_id = job.character_version_id or ""
    out_dir = layout.output_stills_dir(character_id, job_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    contract = snapshot.get("prompt_contract") or {}
    items = sorted(job.items, key=lambda x: x.item_index)

    for item in items:
        if job.cancel_requested:
            job.status = JobStatus.CANCELLED
            job.finished_at = datetime.now(timezone.utc)
            await db.commit()
            return

        req = item.request_json or {}
        positive, negative = render_flux_prompts(
            contract,
            theme=req.get("theme", "portrait"),
            outfit_hint=req.get("outfit_hint"),
            pose_hint=req.get("pose_hint"),
            location_hint=req.get("location_hint"),
            extra_prompt=req.get("extra_prompt"),
        )
        seed = req.get("seed") or random.randint(1, 10**9)
        w, h = 768, 960
        img = Image.new("RGB", (w, h), color=(36, 36, 48))
        draw = ImageDraw.Draw(img)
        title = f"MOCK STILL #{item.item_index}"
        draw.text((24, 24), title, fill=(220, 220, 230))
        draw.text((24, 60), f"seed={seed}", fill=(180, 180, 200))
        draw.text((24, 96), f"theme={req.get('theme')}", fill=(180, 180, 200))
        # wrap prompt snippet
        snippet = (positive[:180] + "…") if len(positive) > 180 else positive
        draw.text((24, 140), snippet[:90], fill=(160, 160, 180))
        draw.text((24, 164), snippet[90:180], fill=(160, 160, 180))
        draw.text((24, h - 80), "SYNTHETIC · 21+", fill=(120, 200, 140))
        draw.text((24, h - 50), "InstantImpact mock pipeline", fill=(120, 120, 140))

        filename = f"still_{item.item_index:03d}_s{seed}.png"
        path = out_dir / filename
        img.save(path, "PNG")
        thumb = out_dir / f"thumb_{item.item_index:03d}.png"
        img.resize((192, 240)).save(thumb, "PNG")

        import hashlib

        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        asset_id = str(uuid.uuid4())
        rel = relative_to_data(path)
        thumb_rel = relative_to_data(thumb)

        disclosure = {
            "synthetic": True,
            "ai_generated": True,
            "age_appearance": "21+",
            "disclosure": SYNTHETIC_DISCLOSURE_DEFAULT,
            "job_id": job_id,
            "seed": seed,
            "pipeline": "mock" if settings.mock_generation else "flux",
        }
        write_json(path.with_suffix(".disclosure.json"), disclosure)

        asset = Asset(
            id=asset_id,
            character_id=character_id,
            character_version_id=version_id,
            job_id=job_id,
            job_item_id=item.id,
            kind="still",
            path=rel,
            thumb_path=thumb_rel,
            sha256=digest,
            width=w,
            height=h,
            seed=seed,
            prompt_positive=positive,
            prompt_negative=negative,
            pipeline="mock",
            meta_json=disclosure,
            decision="pending",
            consistency_score=None,
        )
        db.add(asset)
        item.status = JobItemStatus.DONE
        item.asset_id = asset_id
        await db.flush()

    job.status = JobStatus.COMPLETED
    job.finished_at = datetime.now(timezone.utc)
    if job.brief_id:
        bq = await db.execute(select(ContentBrief).where(ContentBrief.id == job.brief_id))
        brief = bq.scalar_one_or_none()
        if brief:
            brief.status = "completed"
    await db.commit()
