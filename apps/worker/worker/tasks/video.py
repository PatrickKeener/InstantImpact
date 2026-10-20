"""Wan 2.2 image-to-video worker task. Reads snapshots only; never opens SQLite."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

from instantimpact_common.product_media import product_meta_from_item
from instantimpact_common.video import (
    WAN_FRAMES_DEFAULT,
    WAN_FPS_DEFAULT,
    WAN_STEPS_DEFAULT,
    duration_seconds,
    motion_for_item,
    snap_wan_frames,
)
from worker.gpu_lock import GpuLock, is_cancel_requested
from worker.gpu_services import GpuServiceError
from worker.gpu_session import GpuSession
from worker.paths import resolve_request_json
from worker.tasks.garment import apply_garment_tryon, garment_tryon_requested
from worker.tasks.stills import _publish, _resolve_data_dir


async def process_video_job(ctx: dict[str, Any], job_id: str, request_path: str) -> dict[str, Any]:
    redis = ctx["redis"]
    path = resolve_request_json(request_path, job_id)
    if not path.is_file():
        await _publish(
            redis,
            {
                "job_id": job_id,
                "event": "failed",
                "error_code": "missing_request",
                "message": f"request.json not found: {request_path}",
            },
        )
        return {"ok": False}
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    if snapshot.get("mock", True):
        return await _run_mock_video(redis, snapshot, path)

    lock = GpuLock(redis, holder_id=job_id)
    if not await lock.acquire(timeout=3600.0):
        await _publish(
            redis,
            {
                "job_id": job_id,
                "event": "failed",
                "error_code": "gpu_busy",
                "message": "Could not acquire GPU lock within 1 hour",
            },
        )
        return {"ok": False}
    session = GpuSession(kind="stills")
    try:
        message = await session.acquire()
    except GpuServiceError as exc:
        await _publish(
            redis,
            {
                "job_id": job_id,
                "event": "failed",
                "error_code": "gpu_service_pause_failed",
                "message": str(exc),
            },
        )
        await lock.release()
        return {"ok": False}
    try:
        await _publish(redis, {"job_id": job_id, "event": "running", "message": message})
        return await _run_comfy_video(redis, snapshot, path)
    except asyncio.CancelledError:
        with contextlib.suppress(Exception):
            await asyncio.shield(
                _publish(
                    redis,
                    {
                        "job_id": job_id,
                        "event": "failed",
                        "error_code": "job_cancelled",
                        "message": "Video worker was cancelled before completion",
                    },
                )
            )
        raise
    finally:
        await session.release()
        await lock.release()


def _video_source(data_dir: Path, item: dict[str, Any]) -> Path:
    return data_dir / str(item.get("source_image_path") or "").replace("\\", "/").lstrip("/")


def _video_timing(item: dict[str, Any]) -> tuple[int, int]:
    frames = snap_wan_frames(item.get("video_frames") or WAN_FRAMES_DEFAULT)
    fps = int(item.get("video_fps") or WAN_FPS_DEFAULT)
    return frames, max(fps, 1)


def _lookbook_prompt(item: dict[str, Any]) -> str:
    prompt = motion_for_item(
        motion=str(item.get("video_motion") or item.get("extra_prompt") or "").strip(),
        product_kind=item.get("product_kind"),
        product_placement=item.get("product_placement"),
    )
    if item.get("product_name"):
        prompt = (
            f"{prompt}. The person is wearing or presenting {item['product_name']}; "
            "keep garment color, cut, and branding stable through the clip"
        )
    return prompt


async def _run_mock_video(redis: Any, snapshot: dict, request_path: Path) -> dict[str, Any]:
    item = (snapshot.get("items") or [{}])[0]
    job_id = snapshot["job_id"]
    character_id = snapshot.get("character_id") or "unknown"
    data_dir = _resolve_data_dir(request_path)
    source = _video_source(data_dir, item)
    out_dir = data_dir / "outputs" / character_id / job_id / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    poster = out_dir / "poster_000.png"
    if source.is_file():
        shutil.copy2(source, poster)
        if garment_tryon_requested(item):
            from instantimpact_common.product_media import paste_product_corner, resolve_product_image

            pref = resolve_product_image(data_dir, item)
            if pref is not None:
                from PIL import Image

                img = Image.open(poster).convert("RGB")
                img = paste_product_corner(img, pref)
                img.save(poster, "PNG")
    else:
        poster.write_bytes(b"")
    video = out_dir / "video_000.mp4"
    video.write_bytes(b"INSTANTIMPACT_MOCK_VIDEO")
    await _publish(redis, {"job_id": job_id, "event": "item_started", "item_index": 0})
    await _publish(
        redis,
        _done_event(snapshot, item, video, poster, pipeline="mock_video"),
    )
    await _publish(redis, {"job_id": job_id, "event": "completed", "message": "mock video done"})
    return {"ok": True}


async def _run_comfy_video(redis: Any, snapshot: dict, request_path: Path) -> dict[str, Any]:
    from instantimpact_comfy.binder import (
        WAN22_5B_I2V_REQUIRED_VARS,
        bind_workflow,
        load_workflow,
        nodes_only,
        validate_placeholders,
    )
    from instantimpact_comfy.client import ComfyClient
    from PIL import Image

    item = (snapshot.get("items") or [{}])[0]
    job_id = snapshot["job_id"]
    character_id = snapshot.get("character_id") or "unknown"
    data_dir = _resolve_data_dir(request_path)
    source = _video_source(data_dir, item)
    if not source.is_file():
        await _publish(
            redis,
            {
                "job_id": job_id,
                "event": "failed",
                "error_code": "missing_source_still",
                "message": f"Source still not found: {source}",
            },
        )
        return {"ok": False}
    if await is_cancel_requested(redis, job_id):
        await _publish(redis, {"job_id": job_id, "event": "cancelled"})
        return {"ok": False, "cancelled": True}

    await _publish(redis, {"job_id": job_id, "event": "item_started", "item_index": 0})
    client = ComfyClient(
        os.environ.get("INSTANTIMPACT_COMFY_URL", "http://127.0.0.1:8188"),
        timeout=float(os.environ.get("INSTANTIMPACT_VIDEO_TIMEOUT", "3600")),
    )
    workflows_dir = Path(
        os.environ.get(
            "INSTANTIMPACT_WORKFLOWS_DIR",
            str(Path(__file__).resolve().parents[4] / "workflows"),
        )
    )
    out_dir = data_dir / "outputs" / character_id / job_id / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    i2v_source = source
    try_on = garment_tryon_requested(item)
    if try_on:
        dressed = out_dir / "dressed_000.png"
        shutil.copy2(source, dressed)
        await _publish(
            redis,
            {
                "job_id": job_id,
                "event": "log",
                "message": "Dressing the model in the product garment before animating",
            },
        )
        await apply_garment_tryon(
            client=client,
            workflows_dir=workflows_dir,
            data_dir=data_dir,
            still_path=dressed,
            item=item,
            job_id=job_id,
            item_index=0,
            seed=int(item.get("seed") or 1),
        )
        i2v_source = dressed
        await client.free_memory(unload_models=True)

    uploaded = await client.upload_image(
        i2v_source.read_bytes(), f"ii_video_{job_id[:8]}{i2v_source.suffix}"
    )
    template = load_workflow(workflows_dir / "wan22_5b_i2v_vertical_v1.json")
    errors = validate_placeholders(template, WAN22_5B_I2V_REQUIRED_VARS)
    if errors:
        raise RuntimeError("; ".join(errors))
    prompt = _lookbook_prompt(item)
    negative = str(item.get("video_negative") or "").strip() or (
        "static frame, frozen motion, face distortion, identity drift, clothing changes, "
        "warped hands, extra limbs, camera shake, flicker, text, watermark, low quality"
    )
    frames, fps = _video_timing(item)
    variables = {
        "WAN_UNET_NAME": os.environ.get(
            "INSTANTIMPACT_WAN_UNET", "wan2.2_ti2v_5B_fp16.safetensors"
        ),
        "WAN_CLIP_NAME": os.environ.get(
            "INSTANTIMPACT_WAN_CLIP", "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
        ),
        "WAN_VAE_NAME": os.environ.get("INSTANTIMPACT_WAN_VAE", "wan2.2_vae.safetensors"),
        "VIDEO_SOURCE_IMAGE": uploaded,
        "VIDEO_PROMPT": (
            f"Vertical social media marketing video. {prompt}. Preserve the exact person, "
            "face, hairstyle, clothing, garment details, product, background, and lighting "
            "from the first frame. Natural physically plausible motion."
        ),
        "VIDEO_NEGATIVE": negative,
        "VIDEO_WIDTH": 480,
        "VIDEO_HEIGHT": 832,
        "VIDEO_FRAMES": frames,
        "VIDEO_FPS": fps,
        "VIDEO_SEED": int(item.get("seed") or 1),
        "VIDEO_STEPS": int(item.get("video_steps") or WAN_STEPS_DEFAULT),
        "VIDEO_FILENAME_PREFIX": f"ii_video_{job_id[:8]}",
    }
    prompt_id = await client.queue_prompt(nodes_only(bind_workflow(template, variables)))
    entry = await client.wait_for_prompt(prompt_id, timeout=client.timeout)
    candidates = client.files_from_history(entry)
    candidate = next(
        (
            value
            for value in candidates
            if Path(value["filename"]).suffix.lower() in {".mp4", ".webm", ".mov"}
        ),
        None,
    )
    if candidate is None:
        raise RuntimeError("Wan video workflow produced no MP4/WebM/MOV output")
    raw = await client.get_image(
        filename=candidate["filename"],
        subfolder=candidate.get("subfolder") or "",
        folder_type=candidate.get("type") or "output",
    )
    ext = Path(candidate["filename"]).suffix.lower() or ".mp4"
    video = out_dir / f"video_000{ext}"
    video.write_bytes(raw)
    poster = out_dir / "poster_000.png"
    Image.open(i2v_source).convert("RGB").resize((480, 832)).save(poster, "PNG")
    pipeline = "wan2.2-ti2v-5b-lookbook" if try_on else "wan2.2-ti2v-5b"
    event = _done_event(snapshot, item, video, poster, pipeline=pipeline)
    event["sha256"] = hashlib.sha256(raw).hexdigest()
    await _publish(redis, event)
    await _publish(redis, {"job_id": job_id, "event": "completed", "message": "video done"})
    return {"ok": True}


def _done_event(
    snapshot: dict[str, Any],
    item: dict[str, Any],
    video: Path,
    poster: Path,
    *,
    pipeline: str,
) -> dict[str, Any]:
    data_dir = video.parents[4]
    rel_video = str(video.relative_to(data_dir)).replace("\\", "/")
    rel_poster = str(poster.relative_to(data_dir)).replace("\\", "/")
    frames, fps = _video_timing(item)
    product = product_meta_from_item(item)
    meta = {
        "synthetic": True,
        "ai_generated": True,
        "age_appearance": "21+",
        "source_asset_id": item.get("source_asset_id"),
        "motion_prompt": item.get("video_motion"),
        "frames": frames,
        "fps": fps,
        "duration_seconds": duration_seconds(frames, fps),
        "pipeline": pipeline,
        "silent": True,
        "lookbook": garment_tryon_requested(item) or bool(item.get("product_id")),
        **product,
    }
    video.with_suffix(video.suffix + ".disclosure.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    return {
        "job_id": snapshot["job_id"],
        "event": "item_done",
        "item_index": 0,
        "kind": "video",
        "path": rel_video,
        "thumb_path": rel_poster,
        "width": 480,
        "height": 832,
        "seed": item.get("seed"),
        "prompt_positive": item.get("video_motion"),
        "prompt_negative": item.get("video_negative"),
        "pipeline": pipeline,
        "sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
        "meta": meta,
    }
