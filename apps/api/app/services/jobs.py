from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks
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

log = logging.getLogger("instantimpact.jobs")


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
    background_tasks: BackgroundTasks | None = None,
    extra_meta: dict[str, Any] | None = None,
    force_mock: bool | None = None,
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

    # Assign seeds (keep any seed already set, e.g. regenerate)
    base_seed = random.randint(1, 2**31 - 1)
    for i, u in enumerate(units):
        u.aspect_ratio = aspect_ratio
        if u.seed is not None:
            continue
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
        mock=(
            settings.mock_generation or not settings.comfy_enabled
            if force_mock is None
            else force_mock
        ),
        meta={"aspect_ratio": aspect_ratio, "seed_policy": seed_policy, **(extra_meta or {})},
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

    # Prefer ARQ (worker writes files + Redis events). Mock without Redis uses a
    # FastAPI BackgroundTask so the HTTP response is not blocked.
    try:
        await _try_arq_enqueue(job.id, str(request_path), job_type)
    except Exception as e:
        if snapshot.mock:
            log.info("ARQ unavailable (%s) — running mock in background", e)
            if background_tasks is not None:
                background_tasks.add_task(_run_mock_isolated, job.id)
            else:
                await run_mock_job(db, job.id)
        else:
            job = await get_job(db, job.id)
            job.status = JobStatus.FAILED
            job.error_message = f"Failed to enqueue job: {e}"
            job.finished_at = datetime.now(timezone.utc)
            await db.commit()

    return await get_job(db, job.id)


async def _run_mock_isolated(job_id: str) -> None:
    from app.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        try:
            await run_mock_job(session, job_id)
        except Exception:
            log.exception("Isolated mock job failed: %s", job_id)


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
    db: AsyncSession,
    character_id: str,
    payload: SeedGalleryRequest,
    background_tasks: BackgroundTasks | None = None,
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
        background_tasks=background_tasks,
    )
    return job_to_out(job)


async def enqueue_still_batch(
    db: AsyncSession,
    character_id: str,
    payload: StillBatchRequest,
    background_tasks: BackgroundTasks | None = None,
) -> dict:
    units = _expand_brief_items(payload.items)
    if payload.seed is not None and units:
        units[0].seed = int(payload.seed)
        for i, u in enumerate(units[1:], start=1):
            if payload.seed_policy == "fixed_base":
                u.seed = int(payload.seed) + i
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
        background_tasks=background_tasks,
    )
    return job_to_out(job)


async def enqueue_lora_train(
    db: AsyncSession,
    character_id: str,
    *,
    steps: int = 1500,
    strength: float = 0.85,
    min_images: int = 4,
    rebuild_dataset: bool = True,
    background_tasks: BackgroundTasks | None = None,
) -> dict:
    """Build dataset (optional) then enqueue an Ostris AI Toolkit LoRA train job."""
    from app.services import lora as lora_svc
    from instantimpact_common.toolkit import resolve_toolkit_dir

    settings = get_settings()
    explicit = settings.ai_toolkit_dir or None
    toolkit = resolve_toolkit_dir(explicit)
    if not toolkit and not explicit:
        raise JobServiceError(
            "Ostris AI Toolkit not found. On nemesis: clone https://github.com/ostris/ai-toolkit "
            "to /home/pkeener/ai-toolkit, create its venv, accept the FLUX.1-dev license "
            "(huggingface-cli login), then set INSTANTIMPACT_AI_TOOLKIT_DIR in .env.",
            400,
        )

    c = await char_svc.get_character(db, character_id)
    if rebuild_dataset:
        await lora_svc.build_training_dataset(
            db, character_id, decision="approved", min_images=min_images
        )
        c = await char_svc.get_character(db, character_id)

    version = _version_for_generation(c)
    if not version:
        raise JobServiceError("Character has no version")
    layout = get_layout()
    ds_dir = layout.dataset_dir(c.id, version.version_int)
    if not ds_dir.is_dir() or not any(
        p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} for p in ds_dir.iterdir()
    ):
        raise JobServiceError("No training dataset. Approve stills, then train.")

    lora_dir = layout.lora_dir(c.id, version.version_int)
    dest = lora_dir / "model.safetensors"
    training_folder = lora_dir / "toolkit_run"
    trigger = version.trigger_word or f"sks_{c.slug[:40]}_v{version.version_int}"
    run_name = f"ii_{c.slug[:40]}_v{version.version_int}"
    steps = steps or settings.lora_train_steps

    dummy = StillUnitRequest(item_index=0, theme="lora_train", extra_prompt=trigger)
    job = await _enqueue(
        db,
        job_type=JobType.LORA_TRAIN,
        character_id=character_id,
        units=[dummy],
        background_tasks=background_tasks,
        force_mock=False,
        extra_meta={
            "steps": int(steps),
            "strength": float(strength),
            "dataset_dir": str(ds_dir.resolve()),
            "dataset_rel": str(ds_dir.relative_to(layout.root)).replace("\\", "/"),
            "training_folder": str(training_folder.resolve()),
            "training_rel": str(training_folder.relative_to(layout.root)).replace("\\", "/"),
            "dest_path": str(dest.resolve()),
            "dest_rel": str(dest.relative_to(layout.root)).replace("\\", "/"),
            "run_name": run_name,
            "trigger_word": trigger,
            "toolkit_dir": str(toolkit),
            "auto_register": True,
            "slug": c.slug,
            "version_int": version.version_int,
        },
    )
    return job_to_out(job)


async def enqueue_regenerate(
    db: AsyncSession,
    character_id: str,
    asset_id: str,
    *,
    count: int = 1,
    background_tasks: BackgroundTasks | None = None,
) -> dict:
    """Re-run a still using the original brief hints; count=1 reuses the seed."""
    q = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = q.scalar_one_or_none()
    if not asset or asset.character_id != character_id:
        raise JobServiceError("Asset not found", 404)
    req: dict[str, Any] = {}
    if asset.job_item_id:
        iq = await db.execute(select(JobItem).where(JobItem.id == asset.job_item_id))
        item = iq.scalar_one_or_none()
        if item:
            req = item.request_json or {}
    units: list[StillUnitRequest] = []
    for i in range(count):
        units.append(
            StillUnitRequest(
                item_index=i,
                seed=asset.seed if i == 0 else None,
                theme=req.get("theme") or "portrait",
                outfit_hint=req.get("outfit_hint"),
                pose_hint=req.get("pose_hint"),
                location_hint=req.get("location_hint"),
                extra_prompt=req.get("extra_prompt"),
                aspect_ratio=req.get("aspect_ratio") or "4:5",
            )
        )
    job = await _enqueue(
        db,
        job_type=JobType.STILL_BATCH,
        character_id=character_id,
        units=units,
        aspect_ratio=req.get("aspect_ratio") or "4:5",
        seed_policy="random",
        background_tasks=background_tasks,
    )
    return job_to_out(job)


async def cancel_job(db: AsyncSession, job_id: str) -> dict:
    job = await get_job(db, job_id)
    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        return job_to_out(job)
    job.cancel_requested = True
    # Queued orphans (e.g. pre-fix mock jobs) never get a worker/API runner — close them now.
    if job.status == JobStatus.QUEUED:
        job.status = JobStatus.CANCELLED
        job.finished_at = datetime.now(timezone.utc)
        job.error_message = job.error_message or "Cancelled while queued"
        for item in job.items:
            if item.status in (JobItemStatus.PENDING, JobItemStatus.RUNNING):
                item.status = JobItemStatus.SKIPPED
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
            "prompt_negative": a.prompt_negative,
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


def _safe_unlink_under_data(rel_path: str | None) -> bool:
    """Delete a file under data/ if it exists. Returns True if a file was removed."""
    if not rel_path:
        return False
    layout = get_layout()
    root = layout.root.resolve()
    rel = str(rel_path).replace("\\", "/").lstrip("/")
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return False
    if target.is_file():
        target.unlink()
        return True
    return False


def _unlink_asset_files(path: str | None, thumb_path: str | None) -> int:
    """Remove still, thumb, and disclosure sidecars under data/."""
    removed = 0
    for p in (path, thumb_path):
        if _safe_unlink_under_data(p):
            removed += 1
    if path:
        # still_000.png → still_000.disclosure.json (Path.with_suffix)
        p = Path(str(path).replace("\\", "/"))
        for cand in (str(p.with_suffix(".disclosure.json")), f"{path}.disclosure.json"):
            if _safe_unlink_under_data(cand):
                removed += 1
    return removed


async def delete_asset(db: AsyncSession, asset_id: str, *, delete_files: bool = True) -> dict:
    """Permanently remove asset row, ratings, job_item link, and optional media files."""
    from app.db.models import AssetRating

    q = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = q.scalar_one_or_none()
    if not asset:
        raise JobServiceError("Asset not found", 404)

    character_id = asset.character_id
    path = asset.path
    thumb_path = asset.thumb_path

    items = (
        await db.execute(select(JobItem).where(JobItem.asset_id == asset_id))
    ).scalars().all()
    for item in items:
        item.asset_id = None

    ratings = (
        await db.execute(select(AssetRating).where(AssetRating.asset_id == asset_id))
    ).scalars().all()
    for r in ratings:
        await db.delete(r)

    await db.delete(asset)
    await db.commit()

    removed_files = 0
    if delete_files:
        removed_files = _unlink_asset_files(path, thumb_path)

    return {
        "id": asset_id,
        "deleted": True,
        "character_id": character_id,
        "files_removed": removed_files,
    }


async def delete_assets_bulk(
    db: AsyncSession,
    *,
    character_id: str,
    asset_ids: list[str] | None = None,
    decision: str | None = None,
    delete_files: bool = True,
) -> dict:
    """Delete many assets for a character. Filter by ids and/or decision (e.g. rejected)."""
    q = select(Asset).where(Asset.character_id == character_id)
    if asset_ids:
        q = q.where(Asset.id.in_(asset_ids))
    if decision:
        q = q.where(Asset.decision == decision)
    rows = (await db.execute(q)).scalars().all()
    ids = [a.id for a in rows]
    deleted = 0
    files_removed = 0
    for aid in ids:
        result = await delete_asset(db, aid, delete_files=delete_files)
        deleted += 1
        files_removed += int(result.get("files_removed") or 0)
    return {
        "character_id": character_id,
        "deleted": deleted,
        "files_removed": files_removed,
    }


async def apply_job_event(db: AsyncSession, event: dict[str, Any]) -> None:
    """Apply a worker Redis event (sole SQLite writer for real Comfy jobs)."""
    job_id = event.get("job_id")
    if not job_id:
        return
    try:
        job = await get_job(db, str(job_id))
    except JobServiceError:
        return

    name = event.get("event")
    if name == "running":
        if job.status == JobStatus.QUEUED:
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc)
            await db.commit()
        return

    if name == "item_started":
        idx = event.get("item_index")
        for item in job.items:
            if item.item_index == idx and item.status == JobItemStatus.PENDING:
                item.status = JobItemStatus.RUNNING
                break
        if job.status == JobStatus.QUEUED:
            job.status = JobStatus.RUNNING
            job.started_at = job.started_at or datetime.now(timezone.utc)
        await db.commit()
        return

    if name == "cancelled":
        job.status = JobStatus.CANCELLED
        job.finished_at = datetime.now(timezone.utc)
        for item in job.items:
            if item.status in (JobItemStatus.PENDING, JobItemStatus.RUNNING):
                item.status = JobItemStatus.SKIPPED
        await db.commit()
        return

    if name == "failed":
        job.status = JobStatus.FAILED
        job.error_code = event.get("error_code")
        job.error_message = event.get("message")
        job.finished_at = datetime.now(timezone.utc)
        await db.commit()
        return

    if name == "item_failed":
        idx = event.get("item_index")
        for item in job.items:
            if item.item_index == idx:
                item.status = JobItemStatus.FAILED
                item.error_message = event.get("message")
                break
        await db.commit()
        return

    if name == "log":
        return

    if name == "item_done":
        path = event.get("path")
        if not path:
            idx = event.get("item_index")
            item = next((i for i in job.items if i.item_index == idx), None)
            if item and item.status != JobItemStatus.DONE:
                item.status = JobItemStatus.DONE
            if job.status == JobStatus.QUEUED:
                job.status = JobStatus.RUNNING
                job.started_at = job.started_at or datetime.now(timezone.utc)
            if event.get("message"):
                job.error_message = None
            await db.commit()
            return
        idx = event.get("item_index")
        item = next((i for i in job.items if i.item_index == idx), None)
        if not item:
            return
        if item.status == JobItemStatus.DONE and item.asset_id:
            return

        from instantimpact_common.safety_lists import SYNTHETIC_DISCLOSURE_DEFAULT

        asset_id = str(uuid.uuid4())
        meta = event.get("meta") or {
            "synthetic": True,
            "ai_generated": True,
            "disclosure": SYNTHETIC_DISCLOSURE_DEFAULT,
            "pipeline": event.get("pipeline") or "flux",
        }
        asset = Asset(
            id=asset_id,
            character_id=job.character_id or "",
            character_version_id=job.character_version_id or "",
            job_id=job.id,
            job_item_id=item.id,
            kind="still",
            path=str(path),
            thumb_path=event.get("thumb_path"),
            sha256=event.get("sha256") or "",
            width=event.get("width"),
            height=event.get("height"),
            seed=event.get("seed"),
            prompt_positive=event.get("prompt_positive"),
            prompt_negative=event.get("prompt_negative"),
            pipeline=event.get("pipeline") or "flux",
            meta_json=meta,
            decision="pending",
            consistency_score=event.get("consistency_score"),
        )
        db.add(asset)
        item.status = JobItemStatus.DONE
        item.asset_id = asset_id
        item.consistency_score = event.get("consistency_score")
        if job.status == JobStatus.QUEUED:
            job.status = JobStatus.RUNNING
            job.started_at = job.started_at or datetime.now(timezone.utc)
        await db.commit()
        return

    if name == "completed":
        # Mark done even if some items failed (partial success)
        pending = [i for i in job.items if i.status in (JobItemStatus.PENDING, JobItemStatus.RUNNING)]
        for i in pending:
            i.status = JobItemStatus.SKIPPED
        done = sum(1 for i in job.items if i.status == JobItemStatus.DONE)
        failed = sum(1 for i in job.items if i.status == JobItemStatus.FAILED)
        if done == 0 and failed > 0:
            job.status = JobStatus.FAILED
            job.error_message = event.get("message") or "All items failed"
        else:
            job.status = JobStatus.COMPLETED
        job.finished_at = datetime.now(timezone.utc)
        if job.brief_id:
            bq = await db.execute(select(ContentBrief).where(ContentBrief.id == job.brief_id))
            brief = bq.scalar_one_or_none()
            if brief:
                brief.status = "completed" if job.status == JobStatus.COMPLETED else "failed"
        lora_path = event.get("lora_path")
        if (
            job.type == JobType.LORA_TRAIN
            and job.status == JobStatus.COMPLETED
            and lora_path
            and job.character_id
        ):
            try:
                from app.services import lora as lora_svc

                src = str(lora_path)
                layout = get_layout()
                cand = Path(src)
                if not cand.is_file():
                    rel = (job.request_json or {}).get("meta", {}).get("dest_rel")
                    if rel:
                        src = str((layout.root / rel).resolve())
                await lora_svc.register_lora(
                    db,
                    job.character_id,
                    source_path=src,
                    strength=float(event.get("strength") or 0.85),
                    install_to_comfy=True,
                )
                job.error_message = event.get("message") or "LoRA trained and registered"
            except Exception as e:
                job.error_message = f"Train finished but register failed: {e}"
        await db.commit()
        return


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
