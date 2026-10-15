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

from worker.gpu_lock import GpuLock, is_cancel_requested
from worker.gpu_services import GpuServiceError
from worker.gpu_session import GpuSession
from worker.paths import resolve_request_json
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


async def _run_mock_video(redis: Any, snapshot: dict, request_path: Path) -> dict[str, Any]:
    item = (snapshot.get("items") or [{}])[0]
    job_id = snapshot["job_id"]
    character_id = snapshot.get("character_id") or "unknown"
    data_dir = _resolve_data_dir(request_path)
    source = data_dir / str(item.get("source_image_path") or "").replace("\\", "/").lstrip("/")
    out_dir = data_dir / "outputs" / character_id / job_id / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    poster = out_dir / "poster_000.png"
    if source.is_file():
        shutil.copy2(source, poster)
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
    source = data_dir / str(item.get("source_image_path") or "").replace("\\", "/").lstrip("/")
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
    uploaded = await client.upload_image(source.read_bytes(), f"ii_video_{job_id[:8]}{source.suffix}")
    workflows_dir = Path(
        os.environ.get(
            "INSTANTIMPACT_WORKFLOWS_DIR",
            str(Path(__file__).resolve().parents[4] / "workflows"),
        )
    )
    template = load_workflow(workflows_dir / "wan22_5b_i2v_vertical_v1.json")
    errors = validate_placeholders(template, WAN22_5B_I2V_REQUIRED_VARS)
    if errors:
        raise RuntimeError("; ".join(errors))
    prompt = str(item.get("video_motion") or item.get("extra_prompt") or "").strip()
    negative = str(item.get("video_negative") or "").strip() or (
        "static frame, frozen motion, face distortion, identity drift, clothing changes, "
        "warped hands, extra limbs, camera shake, flicker, text, watermark, low quality"
    )
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
        "VIDEO_FRAMES": int(item.get("video_frames") or 81),
        "VIDEO_FPS": int(item.get("video_fps") or 16),
        "VIDEO_SEED": int(item.get("seed") or 1),
        "VIDEO_STEPS": int(item.get("video_steps") or 20),
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
    out_dir = data_dir / "outputs" / character_id / job_id / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(candidate["filename"]).suffix.lower() or ".mp4"
    video = out_dir / f"video_000{ext}"
    video.write_bytes(raw)
    poster = out_dir / "poster_000.png"
    Image.open(source).convert("RGB").resize((480, 832)).save(poster, "PNG")
    event = _done_event(snapshot, item, video, poster, pipeline="wan2.2-ti2v-5b")
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
    frames = int(item.get("video_frames") or 81)
    fps = int(item.get("video_fps") or 16)
    meta = {
        "synthetic": True,
        "ai_generated": True,
        "age_appearance": "21+",
        "source_asset_id": item.get("source_asset_id"),
        "motion_prompt": item.get("video_motion"),
        "frames": frames,
        "fps": fps,
        "duration_seconds": round(frames / fps, 2),
        "pipeline": pipeline,
        "silent": True,
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
