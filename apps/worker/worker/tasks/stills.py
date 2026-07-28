"""Still generation task — loads work from FS request.json only."""

from __future__ import annotations

import hashlib
import io
import json
import os
import uuid
from pathlib import Path
from typing import Any

from worker.gpu_lock import GpuLock, is_cancel_requested

# Aspect → (width, height) for stills
_ASPECT_SIZES: dict[str, tuple[int, int]] = {
    "1:1": (1024, 1024),
    "4:5": (1024, 1280),
    "3:4": (960, 1280),
    "9:16": (768, 1344),
    "16:9": (1344, 768),
}


async def process_still_job(
    ctx: dict[str, Any],
    job_id: str,
    request_path: str,
    job_type: str,
) -> dict[str, Any]:
    """
    Worker entry. Does NOT open SQLite.
    Writes stills under data/outputs and publishes result events for the API consumer.
    """
    redis = ctx["redis"]
    path = Path(request_path)
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
    lock = GpuLock(redis, holder_id=job_id)
    acquired = await lock.acquire(timeout=10.0)
    if not acquired:
        await _publish(
            redis,
            {
                "job_id": job_id,
                "event": "failed",
                "error_code": "gpu_busy",
                "message": "Could not acquire GPU lock",
            },
        )
        return {"ok": False}

    try:
        await _publish(redis, {"job_id": job_id, "event": "running", "message": "GPU acquired"})
        if snapshot.get("mock", True):
            result = await _run_mock(redis, snapshot)
        else:
            result = await _run_comfy(redis, snapshot, request_path=path)
        return result
    finally:
        await lock.release()


async def _run_mock(redis: Any, snapshot: dict) -> dict:
    job_id = snapshot["job_id"]
    items = snapshot.get("items") or []
    for item in items:
        if await is_cancel_requested(redis, job_id):
            await _publish(redis, {"job_id": job_id, "event": "cancelled"})
            return {"ok": False, "cancelled": True}
        await _publish(
            redis,
            {
                "job_id": job_id,
                "event": "item_done",
                "item_index": item.get("item_index"),
                "message": "mock item (API may complete assets)",
            },
        )
    await _publish(
        redis,
        {
            "job_id": job_id,
            "event": "completed",
            "message": "worker mock pass — ensure API mock runner applied assets",
        },
    )
    return {"ok": True}


async def _run_comfy(redis: Any, snapshot: dict, *, request_path: Path) -> dict:
    from instantimpact_comfy.binder import (
        FLUX_STILL_LORA_REQUIRED_VARS,
        FLUX_STILL_REQUIRED_VARS,
        bind_workflow,
        load_workflow,
        nodes_only,
        validate_placeholders,
    )
    from instantimpact_comfy.client import ComfyClient, ComfyClientError
    from instantimpact_prompts.render_flux import render_flux_prompts

    job_id = snapshot["job_id"]
    character_id = snapshot.get("character_id") or "unknown"
    items = snapshot.get("items") or []
    contract = snapshot.get("prompt_contract") or {}
    pipeline_params = snapshot.get("pipeline_params") or {}
    flux_params = pipeline_params.get("flux") or pipeline_params
    trigger = snapshot.get("trigger_word") or (contract.get("trigger_word") if isinstance(contract, dict) else None)
    lora_name = flux_params.get("comfy_lora_name") or None
    lora_strength = float(flux_params.get("lora_strength") if flux_params.get("lora_strength") is not None else 0.85)
    # Also accept bare lora_path basename if it ends with .safetensors and looks installed
    if not lora_name and snapshot.get("lora_path"):
        lp = str(snapshot["lora_path"])
        if lp.endswith(".safetensors"):
            # Prefer ii_* name from register; otherwise basename may not be in Comfy
            pass

    comfy_url = os.environ.get("INSTANTIMPACT_COMFY_URL", "http://127.0.0.1:8188")
    ckpt_name = os.environ.get("INSTANTIMPACT_COMFY_CKPT_NAME", "flux1-dev-fp8.safetensors")
    workflows_dir = Path(
        os.environ.get(
            "INSTANTIMPACT_WORKFLOWS_DIR",
            str(Path(__file__).resolve().parents[4] / "workflows"),
        )
    )
    data_dir = _resolve_data_dir(request_path)
    out_dir = data_dir / "outputs" / character_id / job_id / "stills"
    out_dir.mkdir(parents=True, exist_ok=True)

    use_lora = bool(lora_name)
    wf_name = "flux_still_character_lora_v1.json" if use_lora else "flux_still_character_v1.json"
    required = FLUX_STILL_LORA_REQUIRED_VARS if use_lora else FLUX_STILL_REQUIRED_VARS
    wf_path = workflows_dir / wf_name
    if not wf_path.is_file():
        await _publish(
            redis,
            {
                "job_id": job_id,
                "event": "failed",
                "error_code": "missing_workflow",
                "message": f"Workflow not found: {wf_path}",
            },
        )
        return {"ok": False}

    template = load_workflow(wf_path)
    errors = validate_placeholders(template, required)
    if errors:
        await _publish(
            redis,
            {
                "job_id": job_id,
                "event": "failed",
                "error_code": "workflow_invalid",
                "message": "; ".join(errors),
            },
        )
        return {"ok": False}

    client = ComfyClient(comfy_url, timeout=float(os.environ.get("INSTANTIMPACT_COMFY_TIMEOUT", "600")))
    if not await client.health():
        await _publish(
            redis,
            {
                "job_id": job_id,
                "event": "failed",
                "error_code": "comfy_unreachable",
                "message": f"ComfyUI not healthy at {comfy_url}",
            },
        )
        return {"ok": False}

    # Defaults tuned for flux1-dev-fp8 checkpoint (CFG ~1.0, more steps for detail)
    default_steps = int(flux_params.get("steps") or 28)
    default_cfg = float(flux_params.get("cfg") if flux_params.get("cfg") is not None else 1.0)
    # FP8 checkpoint quality path: force cfg near 1 if someone left SD-like 3.5+
    if default_cfg > 2.0:
        default_cfg = 1.0
    if default_steps < 20:
        default_steps = 28

    meta_aspect = (snapshot.get("meta") or {}).get("aspect_ratio") or "4:5"
    failures = 0

    try:
        from PIL import Image
    except ImportError:
        Image = None  # type: ignore

    for item in items:
        if await is_cancel_requested(redis, job_id):
            await _publish(redis, {"job_id": job_id, "event": "cancelled"})
            return {"ok": False, "cancelled": True}

        item_index = int(item.get("item_index") or 0)
        theme = item.get("theme") or "portrait"
        seed = int(item.get("seed") or 0) or int(uuid.uuid4().int % (2**31 - 1))
        aspect = item.get("aspect_ratio") or meta_aspect
        width, height = _size_for_aspect(aspect, flux_params)

        positive, negative = render_flux_prompts(
            contract,
            theme=theme,
            outfit_hint=item.get("outfit_hint"),
            pose_hint=item.get("pose_hint"),
            location_hint=item.get("location_hint"),
            extra_prompt=item.get("extra_prompt"),
        )
        # Soft adult / synthetic bias for character stills (not a safety replacement)
        if "adult" not in positive.lower() and "21" not in positive:
            positive = f"adult woman 25 years old, {positive}" if positive else "adult woman 25 years old"
        # Ensure trigger token is present when using a character LoRA
        if trigger and trigger not in positive:
            positive = f"{trigger}, {positive}"

        prefix = f"ii_{job_id[:8]}_{item_index:03d}"
        variables = {
            "CKPT_NAME": ckpt_name,
            "POSITIVE_PROMPT": positive,
            "NEGATIVE_PROMPT": negative or "",
            "SEED": seed,
            "WIDTH": width,
            "HEIGHT": height,
            "STEPS": int(item.get("steps") or default_steps),
            "CFG": float(item.get("cfg") or default_cfg),
            "FILENAME_PREFIX": prefix,
        }
        if use_lora:
            variables["LORA_NAME"] = lora_name
            variables["LORA_STRENGTH"] = lora_strength

        try:
            bound = bind_workflow(template, variables)
            prompt_graph = nodes_only(bound)
            prompt_id = await client.queue_prompt(prompt_graph)
            entry = await client.wait_for_prompt(prompt_id, timeout=client.timeout)
            images = ComfyClient.images_from_history(entry)
            if not images:
                raise ComfyClientError(f"No images in Comfy history for prompt {prompt_id}")

            img_meta = images[0]
            raw = await client.get_image(
                filename=img_meta["filename"],
                subfolder=img_meta.get("subfolder") or "",
                folder_type=img_meta.get("type") or "output",
            )

            still_name = f"still_{item_index:03d}_s{seed}.png"
            still_path = out_dir / still_name
            still_path.write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()

            thumb_name = f"thumb_{item_index:03d}.png"
            thumb_path = out_dir / thumb_name
            w_out, h_out = width, height
            if Image is not None:
                im = Image.open(io.BytesIO(raw)).convert("RGB")
                w_out, h_out = im.size
                tw = 192
                th = max(1, int(192 * h_out / max(w_out, 1)))
                im.resize((tw, th)).save(thumb_path, "PNG")
            else:
                thumb_path.write_bytes(raw)

            # paths relative to data/
            rel_still = str(still_path.relative_to(data_dir)).replace("\\", "/")
            rel_thumb = str(thumb_path.relative_to(data_dir)).replace("\\", "/")

            disclosure = {
                "synthetic": True,
                "ai_generated": True,
                "age_appearance": "21+",
                "pipeline": "flux",
                "comfy_prompt_id": prompt_id,
                "ckpt": ckpt_name,
                "job_id": job_id,
                "seed": seed,
            }
            still_path.with_suffix(".disclosure.json").write_text(
                json.dumps(disclosure, indent=2), encoding="utf-8"
            )

            await _publish(
                redis,
                {
                    "job_id": job_id,
                    "event": "item_done",
                    "item_index": item_index,
                    "path": rel_still,
                    "thumb_path": rel_thumb,
                    "width": w_out,
                    "height": h_out,
                    "seed": seed,
                    "prompt_positive": positive,
                    "prompt_negative": negative,
                    "sha256": digest,
                    "pipeline": "flux",
                    "meta": disclosure,
                },
            )
        except Exception as e:
            failures += 1
            await _publish(
                redis,
                {
                    "job_id": job_id,
                    "event": "item_failed",
                    "item_index": item_index,
                    "error_code": "comfy_item_failed",
                    "message": str(e),
                },
            )
            if not snapshot.get("resume_on_item_failure", True):
                await _publish(
                    redis,
                    {
                        "job_id": job_id,
                        "event": "failed",
                        "error_code": "comfy_item_failed",
                        "message": str(e),
                    },
                )
                return {"ok": False}

    if failures and failures >= len(items):
        await _publish(
            redis,
            {
                "job_id": job_id,
                "event": "failed",
                "error_code": "comfy_all_items_failed",
                "message": f"All {failures} items failed",
            },
        )
        return {"ok": False}

    await _publish(
        redis,
        {
            "job_id": job_id,
            "event": "completed",
            "message": f"Comfy stills done ({len(items) - failures}/{len(items)})",
            "failures": failures,
        },
    )
    return {"ok": True, "failures": failures}


def _resolve_data_dir(request_path: Path) -> Path:
    env = os.environ.get("INSTANTIMPACT_DATA_DIR")
    if env:
        return Path(env).resolve()
    # request.json lives at data/jobs/{id}/request.json
    return request_path.resolve().parents[1]


def _size_for_aspect(aspect: str, flux_params: dict) -> tuple[int, int]:
    if flux_params.get("width") and flux_params.get("height"):
        return int(flux_params["width"]), int(flux_params["height"])
    return _ASPECT_SIZES.get(aspect, (1024, 1280))


async def _publish(redis: Any, event: dict) -> None:
    payload = json.dumps(event)
    await redis.rpush("instantimpact:job_events", payload)
    await redis.publish("instantimpact:job_events", payload)
