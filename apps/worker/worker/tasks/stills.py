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
from worker.paths import resolve_request_json

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
    is_mock = bool(snapshot.get("mock", True))

    if is_mock:
        await _publish(redis, {"job_id": job_id, "event": "running", "message": "mock generation"})
        return await _run_mock(redis, snapshot, request_path=path)

    lock = GpuLock(redis, holder_id=job_id)
    acquired = await lock.acquire(timeout=3600.0)
    if not acquired:
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

    try:
        await _publish(redis, {"job_id": job_id, "event": "running", "message": "GPU acquired"})
        return await _run_comfy(redis, snapshot, request_path=path)
    finally:
        await lock.release()


def _refs_dir(snapshot: dict, data_dir: Path) -> Path | None:
    raw = snapshot.get("ref_pack_path")
    if not raw:
        return None
    p = Path(str(raw))
    if not p.is_absolute():
        p = data_dir / str(raw).replace("\\", "/").lstrip("/")
    return p if p.is_dir() else None


def _score_against_refs(still_path: Path, refs: Path | None) -> float | None:
    try:
        from instantimpact_common.similarity import best_ref_similarity

        return best_ref_similarity(still_path, refs)
    except Exception:
        return None


async def _run_mock(redis: Any, snapshot: dict, *, request_path: Path) -> dict:
    """Write placeholder stills + publish item_done with paths (API is still the DB writer)."""
    from instantimpact_common.safety_lists import SYNTHETIC_DISCLOSURE_DEFAULT
    from instantimpact_prompts.render_flux import render_flux_prompts

    try:
        from PIL import Image, ImageDraw
    except ImportError:
        await _publish(
            redis,
            {
                "job_id": snapshot["job_id"],
                "event": "failed",
                "error_code": "missing_pillow",
                "message": "Pillow is required for mock stills",
            },
        )
        return {"ok": False}

    job_id = snapshot["job_id"]
    character_id = snapshot.get("character_id") or "unknown"
    items = snapshot.get("items") or []
    data_dir = _resolve_data_dir(request_path)
    out_dir = data_dir / "outputs" / character_id / job_id / "stills"
    out_dir.mkdir(parents=True, exist_ok=True)
    contract = snapshot.get("prompt_contract") or {}
    refs = _refs_dir(snapshot, data_dir)

    for item in items:
        if await is_cancel_requested(redis, job_id):
            await _publish(redis, {"job_id": job_id, "event": "cancelled"})
            return {"ok": False, "cancelled": True}

        item_index = int(item.get("item_index") or 0)
        await _publish(
            redis,
            {"job_id": job_id, "event": "item_started", "item_index": item_index},
        )
        theme = item.get("theme") or "portrait"
        seed = int(item.get("seed") or 0) or int(uuid.uuid4().int % (2**31 - 1))
        positive, negative = render_flux_prompts(
            contract,
            theme=theme,
            outfit_hint=item.get("outfit_hint"),
            pose_hint=item.get("pose_hint"),
            location_hint=item.get("location_hint"),
            extra_prompt=item.get("extra_prompt"),
            product_name=item.get("product_name"),
            product_description=item.get("product_description"),
            product_placement=item.get("product_placement"),
        )
        w, h = 768, 960
        img = Image.new("RGB", (w, h), color=(36, 36, 48))
        draw = ImageDraw.Draw(img)
        draw.text((24, 24), f"MOCK STILL #{item_index}", fill=(220, 220, 230))
        draw.text((24, 60), f"seed={seed}", fill=(180, 180, 200))
        draw.text((24, 96), f"theme={theme}", fill=(180, 180, 200))
        if item.get("product_name"):
            draw.text(
                (24, 120),
                f"product={item.get('product_name')} ({item.get('product_placement') or 'holding'})",
                fill=(200, 180, 140),
            )
        snippet = (positive[:180] + "…") if len(positive) > 180 else positive
        y0 = 148 if item.get("product_name") else 140
        draw.text((24, y0), snippet[:90], fill=(160, 160, 180))
        draw.text((24, y0 + 24), snippet[90:180], fill=(160, 160, 180))
        draw.text((24, h - 80), "SYNTHETIC · 21+", fill=(120, 200, 140))
        draw.text((24, h - 50), "InstantImpact mock pipeline", fill=(120, 120, 140))

        from instantimpact_common.product_media import (
            paste_product_corner,
            product_meta_from_item,
            resolve_product_image,
        )

        pref = resolve_product_image(data_dir, item)
        if pref is not None:
            try:
                img = paste_product_corner(img, pref)
            except Exception:
                pass

        still_name = f"still_{item_index:03d}_s{seed}.png"
        still_path = out_dir / still_name
        img.save(still_path, "PNG")
        thumb_path = out_dir / f"thumb_{item_index:03d}.png"
        img.resize((192, 240)).save(thumb_path, "PNG")
        digest = hashlib.sha256(still_path.read_bytes()).hexdigest()
        rel_still = str(still_path.relative_to(data_dir)).replace("\\", "/")
        rel_thumb = str(thumb_path.relative_to(data_dir)).replace("\\", "/")
        disclosure = {
            "synthetic": True,
            "ai_generated": True,
            "age_appearance": "21+",
            "disclosure": SYNTHETIC_DISCLOSURE_DEFAULT,
            "job_id": job_id,
            "seed": seed,
            "pipeline": "mock",
            **product_meta_from_item(item),
        }
        still_path.with_suffix(".disclosure.json").write_text(
            json.dumps(disclosure, indent=2), encoding="utf-8"
        )
        score = _score_against_refs(still_path, refs)
        await _publish(
            redis,
            {
                "job_id": job_id,
                "event": "item_done",
                "item_index": item_index,
                "path": rel_still,
                "thumb_path": rel_thumb,
                "width": w,
                "height": h,
                "seed": seed,
                "prompt_positive": positive,
                "prompt_negative": negative,
                "sha256": digest,
                "pipeline": "mock",
                "consistency_score": score,
                "meta": disclosure,
            },
        )

    await _publish(
        redis,
        {"job_id": job_id, "event": "completed", "message": f"mock stills done ({len(items)})"},
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
    from instantimpact_common.offline import enforce_strict_offline
    from instantimpact_prompts.render_flux import render_flux_encoder_prompts

    job_id = snapshot["job_id"]
    character_id = snapshot.get("character_id") or "unknown"
    items = snapshot.get("items") or []
    contract = snapshot.get("prompt_contract") or {}
    pipeline_params = snapshot.get("pipeline_params") or {}
    flux_params = pipeline_params.get("flux") or pipeline_params
    trigger = snapshot.get("trigger_word") or (
        contract.get("trigger_word") if isinstance(contract, dict) else None
    )
    lora_name = flux_params.get("comfy_lora_name") or None
    lora_strength = float(
        flux_params.get("lora_strength") if flux_params.get("lora_strength") is not None else 0.85
    )
    lora_clip_strength = float(
        flux_params.get("lora_clip_strength")
        if flux_params.get("lora_clip_strength") is not None
        else 0.55
    )
    if not lora_name and snapshot.get("lora_path"):
        lp = str(snapshot["lora_path"])
        if lp.endswith(".safetensors"):
            lora_name = Path(lp).name

    comfy_url = os.environ.get("INSTANTIMPACT_COMFY_URL", "http://127.0.0.1:8188")
    strict = os.environ.get("INSTANTIMPACT_STRICT_OFFLINE", "").lower() in {"1", "true", "yes"}
    try:
        enforce_strict_offline(comfy_url, strict)
    except RuntimeError as e:
        await _publish(
            redis,
            {
                "job_id": job_id,
                "event": "failed",
                "error_code": "strict_offline",
                "message": str(e),
            },
        )
        return {"ok": False}

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
    refs = _refs_dir(snapshot, data_dir)

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

    client = ComfyClient(
        comfy_url, timeout=float(os.environ.get("INSTANTIMPACT_COMFY_TIMEOUT", "600"))
    )
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

    default_steps = int(flux_params.get("steps") or 28)
    # Flux Dev is guidance-distilled: KSampler CFG stays 1.0.
    # Prompt adherence is the CLIPTextEncodeFlux guidance input.
    default_cfg = 1.0
    default_guidance = float(
        flux_params.get("guidance") if flux_params.get("guidance") is not None else 2.5
    )
    default_guidance = max(1.0, min(default_guidance, 5.0))
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
        await _publish(
            redis,
            {"job_id": job_id, "event": "item_started", "item_index": item_index},
        )
        theme = item.get("theme") or "portrait"
        seed = int(item.get("seed") or 0) or int(uuid.uuid4().int % (2**31 - 1))
        aspect = item.get("aspect_ratio") or meta_aspect
        width, height = _size_for_aspect(aspect, flux_params)

        clip_l, positive, negative = render_flux_encoder_prompts(
            contract,
            theme=theme,
            outfit_hint=item.get("outfit_hint"),
            pose_hint=item.get("pose_hint"),
            location_hint=item.get("location_hint"),
            extra_prompt=item.get("extra_prompt"),
            product_name=item.get("product_name"),
            product_description=item.get("product_description"),
            product_placement=item.get("product_placement"),
        )
        age_min = int(snapshot.get("age_appearance_min") or 21)
        clip_l = _ensure_adult_prompt(clip_l, age_appearance_min=age_min)
        positive = _ensure_adult_prompt(positive, age_appearance_min=age_min)
        if trigger and trigger not in clip_l:
            clip_l = f"{trigger}, {clip_l}"
        if trigger and trigger not in positive:
            positive = f"{trigger}, {positive}"

        prefix = f"ii_{job_id[:8]}_{item_index:03d}"
        variables = {
            "CKPT_NAME": ckpt_name,
            "CLIP_L_PROMPT": clip_l,
            "POSITIVE_PROMPT": positive,
            "NEGATIVE_PROMPT": negative or "",
            "SEED": seed,
            "WIDTH": width,
            "HEIGHT": height,
            "STEPS": int(item.get("steps") or default_steps),
            "CFG": default_cfg,
            "GUIDANCE": default_guidance,
            "FILENAME_PREFIX": prefix,
        }
        if use_lora:
            variables["LORA_NAME"] = lora_name
            variables["LORA_STRENGTH"] = lora_strength
            variables["LORA_CLIP_STRENGTH"] = lora_clip_strength

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

            rel_still = str(still_path.relative_to(data_dir)).replace("\\", "/")
            rel_thumb = str(thumb_path.relative_to(data_dir)).replace("\\", "/")

            from instantimpact_common.product_media import product_meta_from_item

            disclosure = {
                "synthetic": True,
                "ai_generated": True,
                "age_appearance": "21+",
                "pipeline": "flux",
                "comfy_prompt_id": prompt_id,
                "ckpt": ckpt_name,
                "steps": variables["STEPS"],
                "guidance": default_guidance,
                "cfg": default_cfg,
                "job_id": job_id,
                "seed": seed,
                "lora_name": lora_name,
                "lora_strength": lora_strength if use_lora else None,
                "lora_clip_strength": lora_clip_strength if use_lora else None,
                "clip_l_prompt": clip_l,
                "ref_pack": str(refs) if refs else None,
                **product_meta_from_item(item),
            }
            still_path.with_suffix(".disclosure.json").write_text(
                json.dumps(disclosure, indent=2), encoding="utf-8"
            )
            score = _score_against_refs(still_path, refs)

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
                    "consistency_score": score,
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
    # request.json lives at data/jobs/{id}/request.json → parents[2] == data/
    return request_path.resolve().parents[2]


def _size_for_aspect(aspect: str, flux_params: dict) -> tuple[int, int]:
    if (
        flux_params.get("override_dimensions")
        and flux_params.get("width")
        and flux_params.get("height")
    ):
        return int(flux_params["width"]), int(flux_params["height"])
    return _ASPECT_SIZES.get(aspect, (1024, 1280))


def _ensure_adult_prompt(positive: str, *, age_appearance_min: int) -> str:
    """Add the character's actual adult age floor only when the contract omitted one."""
    if "adult" in positive.lower() or "21" in positive:
        return positive
    age = max(21, age_appearance_min)
    prefix = f"clearly adult woman, {age}+ appearance"
    return f"{prefix}, {positive}" if positive else prefix


async def _publish(redis: Any, event: dict) -> None:
    payload = json.dumps(event)
    await redis.rpush("instantimpact:job_events", payload)
    await redis.publish("instantimpact:job_events", payload)
