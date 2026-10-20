"""Qwen Image Edit garment try-on used by still and lookbook-video jobs."""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any


def garment_tryon_requested(item: dict[str, Any]) -> bool:
    if item.get("skip_garment_tryon"):
        return False
    return (
        item.get("product_kind") == "garment"
        and item.get("product_placement") == "wearing"
        and bool(item.get("product_ref_path"))
    )


def resolve_garment_path(data_dir: Path, item: dict[str, Any]) -> Path:
    garment_path = Path(str(item["product_ref_path"]))
    if not garment_path.is_absolute():
        garment_path = data_dir / str(garment_path).replace("\\", "/").lstrip("/")
    if not garment_path.is_file():
        raise RuntimeError(f"Garment reference is missing: {garment_path}")
    return garment_path


async def apply_garment_tryon(
    *,
    client: Any,
    workflows_dir: Path,
    data_dir: Path,
    still_path: Path,
    item: dict[str, Any],
    job_id: str,
    item_index: int,
    seed: int,
) -> None:
    """Transfer an uploaded garment onto a still via local Qwen Image Edit."""
    from instantimpact_comfy.binder import (
        QWEN_GARMENT_REQUIRED_VARS,
        bind_workflow,
        load_workflow,
        nodes_only,
        validate_placeholders,
    )
    from PIL import Image, ImageDraw

    garment_path = resolve_garment_path(data_dir, item)
    person = Image.open(still_path).convert("RGB")
    garment = Image.open(garment_path).convert("RGB")
    panel_w = max(220, int(person.width * 0.34))
    panel_h = max(260, int(person.height * 0.42))
    garment.thumbnail((panel_w - 24, panel_h - 48))
    composite = person.copy()
    draw = ImageDraw.Draw(composite)
    left = person.width - panel_w - 16
    top = person.height - panel_h - 16
    draw.rounded_rectangle(
        (left, top, person.width - 16, person.height - 16),
        radius=12,
        fill=(245, 245, 245),
        outline=(20, 20, 20),
        width=3,
    )
    gx = left + (panel_w - garment.width) // 2
    gy = top + 28 + (panel_h - 40 - garment.height) // 2
    composite.paste(garment, (gx, gy))
    draw.text((left + 10, top + 8), "GARMENT REFERENCE", fill=(10, 10, 10))
    buf = io.BytesIO()
    composite.save(buf, "PNG")
    uploaded = await client.upload_image(
        buf.getvalue(), f"ii_tryon_{job_id[:8]}_{item_index:03d}.png"
    )

    garment_bits = ", ".join(
        f"{key}: {value}" for key, value in (item.get("garment") or {}).items() if value
    )
    prompt = (
        "Edit the person in the image so she is wearing the garment shown in the "
        "GARMENT REFERENCE panel. Preserve her face, hair, body, pose, hands, background, "
        "camera framing, and photorealistic lighting. Reproduce the garment's exact color, "
        "material, pattern, cut, seams, trim, and visible branding. Remove the reference "
        "panel completely from the final image."
    )
    if garment_bits:
        prompt += f" Garment specification: {garment_bits}."
    if item.get("garment_styling"):
        prompt += f" Styling and fit: {item['garment_styling']}."
    if item.get("accessories"):
        prompt += f" Accessories: {item['accessories']}."

    wf_path = workflows_dir / "qwen_garment_tryon_v1.json"
    template = load_workflow(wf_path)
    errors = validate_placeholders(template, QWEN_GARMENT_REQUIRED_VARS)
    if errors:
        raise RuntimeError("; ".join(errors))
    variables = {
        "QWEN_UNET_NAME": os.environ.get(
            "INSTANTIMPACT_QWEN_EDIT_UNET", "qwen_image_edit_fp8_e4m3fn.safetensors"
        ),
        "QWEN_CLIP_NAME": os.environ.get(
            "INSTANTIMPACT_QWEN_EDIT_CLIP", "qwen_2.5_vl_7b_fp8_scaled.safetensors"
        ),
        "QWEN_VAE_NAME": os.environ.get(
            "INSTANTIMPACT_QWEN_EDIT_VAE", "qwen_image_vae.safetensors"
        ),
        "QWEN_LORA_NAME": os.environ.get(
            "INSTANTIMPACT_QWEN_EDIT_LORA",
            "Qwen-Image-Edit-Lightning-4steps-V1.0-bf16.safetensors",
        ),
        "TRYON_INPUT_IMAGE": uploaded,
        "TRYON_PROMPT": prompt,
        "TRYON_NEGATIVE": (
            "reference panel, split screen, collage, duplicate person, changed face, "
            "changed pose, wrong garment, wrong color, extra limbs, text overlay"
        ),
        "TRYON_SEED": seed,
        "TRYON_FILENAME_PREFIX": f"ii_tryon_{job_id[:8]}_{item_index:03d}",
    }
    prompt_id = await client.queue_prompt(nodes_only(bind_workflow(template, variables)))
    entry = await client.wait_for_prompt(prompt_id, timeout=client.timeout)
    images = client.images_from_history(entry)
    if not images:
        raise RuntimeError("Qwen garment workflow produced no image")
    output = images[0]
    raw = await client.get_image(
        filename=output["filename"],
        subfolder=output.get("subfolder") or "",
        folder_type=output.get("type") or "output",
    )
    edited = Image.open(io.BytesIO(raw)).convert("RGB")
    if edited.size != person.size:
        edited = edited.resize(person.size)
    edited.save(still_path, "PNG")
