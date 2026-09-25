"""Character LoRA dataset build + weight registration (identity lock path)."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Asset
from app.services.characters import (
    CharacterServiceError,
    _working_version,
    character_to_out,
    get_character,
)
from app.services.storage import get_layout, write_json
from instantimpact_common.enums import CharacterStatus
from instantimpact_prompts.contract import build_prompt_contract

MIN_IMAGES_SOFT = 8
MIN_IMAGES_HARD = 4  # allow small tests; UI warns below 12


def _safe_data_path(rel: str) -> Path | None:
    layout = get_layout()
    root = layout.root.resolve()
    target = (root / str(rel).replace("\\", "/").lstrip("/")).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    return target if target.is_file() else None


def _caption_for_asset(*, trigger: str, asset: Asset) -> str:
    """Trigger + pose/light/outfit. Identity stays on the trigger for LoRA."""
    from instantimpact_prompts.train_caption import caption_from_asset

    return caption_from_asset(trigger=trigger, asset=asset)


async def build_training_dataset(
    db: AsyncSession,
    character_id: str,
    *,
    decision: str = "approved",
    min_images: int = MIN_IMAGES_HARD,
) -> dict[str, Any]:
    """
    Copy curated stills into version dataset/ with .txt captions + AI Toolkit stub config.
    Also refreshes refs/ with copies of approved images.
    """
    c = await get_character(db, character_id)
    if c.status == CharacterStatus.ARCHIVED:
        raise CharacterServiceError("Cannot build dataset for archived character")
    if not c.synthetic_confirmed or not c.not_real_person_attested:
        raise CharacterServiceError("Confirm synthetic + not-real-person first")

    version = _working_version(c)
    if not version:
        raise CharacterServiceError("No character version")

    q = (
        select(Asset)
        .where(Asset.character_id == character_id)
        .where(Asset.kind == "still")
        .where(Asset.decision == decision)
        .order_by(Asset.created_at.desc())
    )
    assets = list((await db.execute(q)).scalars().all())
    if len(assets) < min_images:
        raise CharacterServiceError(
            f"Need at least {min_images} {decision} stills to build a dataset "
            f"(have {len(assets)}). Approve more photo-quality images first.",
            400,
        )

    layout = get_layout()
    ds_dir = layout.dataset_dir(c.id, version.version_int)
    refs_dir = layout.refs_dir(c.id, version.version_int)
    lora_dir = layout.lora_dir(c.id, version.version_int)
    for d in (ds_dir, refs_dir, lora_dir):
        d.mkdir(parents=True, exist_ok=True)

    # Clear previous dataset images (keep folder)
    for old in ds_dir.glob("*"):
        if old.is_file() and old.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".txt"}:
            old.unlink()

    trigger = version.trigger_word or f"sks_{c.slug[:40]}_v{version.version_int}"
    version.trigger_word = trigger
    appearance = version.appearance_json or {}

    copied = 0
    captions: list[dict[str, Any]] = []
    for i, asset in enumerate(assets):
        src = _safe_data_path(asset.path)
        if not src:
            continue
        ext = src.suffix.lower() or ".png"
        if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
            ext = ".png"
        stem = f"{i + 1:03d}"
        dest = ds_dir / f"{stem}{ext}"
        shutil.copy2(src, dest)
        cap = _caption_for_asset(trigger=trigger, asset=asset)
        (ds_dir / f"{stem}.txt").write_text(cap + "\n", encoding="utf-8")
        captions.append({"file": dest.name, "caption": cap, "asset_id": asset.id})
        # First few into refs pack
        if i < 8:
            ref_name = f"ref_{stem}{ext}"
            shutil.copy2(src, refs_dir / ref_name)
        if i == 0:
            shutil.copy2(src, refs_dir / f"face_primary{ext}")
        copied += 1

    if copied < min_images:
        raise CharacterServiceError(
            f"Only {copied} image files could be read from disk (need {min_images})",
            400,
        )

    # Rebuild prompt contract with trigger
    contract = build_prompt_contract(
        appearance=appearance,
        boundaries=version.boundaries_json or {},
        trigger_word=trigger,
    )
    version.prompt_contract_json = contract.model_dump()
    version.ref_pack_path = str(refs_dir.relative_to(layout.root)).replace("\\", "/")

    dim = max(8, min(int(get_settings().lora_dim), 128))
    train_cfg = {
        "tool": "ostris_ai_toolkit",
        "base": "flux",
        "trigger_word": trigger,
        "dataset_dir": str(ds_dir),
        "output_dir": str(lora_dir),
        "network": {"type": "lora", "linear": dim, "linear_alpha": dim},
        "steps_suggested": 1500,
        "lr_suggested": 1e-4,
        "resolution": 1024,
        "notes": (
            "Train with Ostris AI Toolkit (or compatible Flux LoRA trainer). "
            "Place final weights as model.safetensors in output_dir, then "
            "POST /api/characters/{id}/lora/register."
        ),
        "image_count": copied,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "decision_filter": decision,
    }
    write_json(lora_dir / "train_config.json", train_cfg)
    write_json(ds_dir / "manifest.json", {"trigger": trigger, "items": captions})

    # First-time path: mark training until LoRA registered + locked
    if not c.locked_version_id and c.status in (
        CharacterStatus.DRAFT,
        CharacterStatus.BOOTSTRAP,
        CharacterStatus.TRAINING,
    ):
        c.status = CharacterStatus.TRAINING

    c.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "character": character_to_out(await get_character(db, character_id)),
        "dataset_dir": str(ds_dir.relative_to(layout.root)).replace("\\", "/"),
        "refs_dir": str(refs_dir.relative_to(layout.root)).replace("\\", "/"),
        "lora_dir": str(lora_dir.relative_to(layout.root)).replace("\\", "/"),
        "trigger_word": trigger,
        "image_count": copied,
        "train_config": train_cfg,
        "warning": (
            None
            if copied >= 12
            else f"Only {copied} images — aim for 12–30 approved photo stills for a stronger LoRA."
        ),
    }


def _resolve_lora_source(source_path: str, data_root: Path) -> Path | None:
    """Accept host paths, Docker /app/data paths, or paths relative to data/."""
    raw = str(source_path).strip().replace("\\", "/")
    candidates: list[Path] = [Path(raw).expanduser()]
    rel = _safe_data_path(raw)
    if rel:
        candidates.append(rel)
    for prefix in ("/home/pkeener/InstantImpact/data/", "/app/data/"):
        if raw.startswith(prefix):
            candidates.append(data_root / raw[len(prefix) :])
    if "/data/characters/" in raw:
        candidates.append(data_root / raw.split("/data/", 1)[1])
    if not Path(raw).is_absolute():
        candidates.append(data_root / raw.lstrip("/"))
    seen: set[str] = set()
    for c in candidates:
        try:
            p = c.resolve()
        except OSError:
            continue
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        if p.is_file():
            return p
    return None


async def register_lora(
    db: AsyncSession,
    character_id: str,
    *,
    source_path: str,
    strength: float = 0.85,
    install_to_comfy: bool = True,
) -> dict[str, Any]:
    """
    Install a trained .safetensors into the character version + Comfy loras folder.
    source_path: absolute path on the server, or path relative to data/.
    """
    c = await get_character(db, character_id)
    version = _working_version(c)
    if not version:
        raise CharacterServiceError("No character version")

    layout = get_layout()
    src = _resolve_lora_source(source_path, layout.root)
    if src is None or not src.is_file():
        raise CharacterServiceError(
            f"LoRA file not found or not readable: {source_path}", 404
        )
    if src.suffix.lower() != ".safetensors":
        raise CharacterServiceError("LoRA must be a .safetensors file")
    allowed_roots = [layout.root.resolve()]
    comfy_loras = Path(get_settings().comfy_loras_dir).expanduser()
    try:
        allowed_roots.append(comfy_loras.resolve())
    except Exception:
        pass
    allowed = False
    for root in allowed_roots:
        try:
            src.relative_to(root)
            allowed = True
            break
        except ValueError:
            continue
    if not allowed:
        raise CharacterServiceError(
            "LoRA source must be under data/ or INSTANTIMPACT_COMFY_LORAS_DIR"
        )

    lora_dir = layout.lora_dir(c.id, version.version_int)
    try:
        lora_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        raise CharacterServiceError(
            f"Cannot write to {lora_dir} (permission denied). "
            f"chown the data/ tree to the API user. Detail: {e}",
            500,
        ) from e

    dest = (lora_dir / "model.safetensors").resolve()
    try:
        # Already in the right place (common after manual cp) — do not shutil.copy2 same file
        if src != dest:
            shutil.copy2(src, dest)
    except shutil.SameFileError:
        pass
    except PermissionError as e:
        raise CharacterServiceError(
            f"Cannot write LoRA to {dest}: {e}. Fix ownership or copy as the API user.",
            500,
        ) from e

    comfy_name = f"ii_{c.slug}_v{version.version_int:03d}.safetensors"
    comfy_installed = None
    settings = get_settings()
    if install_to_comfy:
        comfy_loras = Path(settings.comfy_loras_dir).expanduser()
        try:
            comfy_loras.mkdir(parents=True, exist_ok=True)
            target = comfy_loras / comfy_name
            if dest != target.resolve():
                shutil.copy2(dest, target)
            comfy_installed = str(target)
        except PermissionError as e:
            raise CharacterServiceError(
                f"Cannot install LoRA into Comfy folder {comfy_loras}: {e}. "
                f"Set INSTANTIMPACT_COMFY_LORAS_DIR or chown that directory. "
                f"Character path was saved; Comfy install failed.",
                500,
            ) from e

    try:
        version.lora_path = str(dest.relative_to(layout.root)).replace("\\", "/")
    except ValueError:
        # dest outside data root — store absolute
        version.lora_path = str(dest)

    params = dict(version.pipeline_params_json or {})
    flux = dict(params.get("flux") or {})
    flux["lora_strength"] = float(strength)
    flux["comfy_lora_name"] = comfy_name
    params["flux"] = flux
    version.pipeline_params_json = params

    # Ensure trigger in contract
    trigger = version.trigger_word or f"sks_{c.slug[:40]}_v{version.version_int}"
    version.trigger_word = trigger
    try:
        version.prompt_contract_json = build_prompt_contract(
            appearance=version.appearance_json or {},
            boundaries=version.boundaries_json or {},
            trigger_word=trigger,
        ).model_dump()
    except Exception as e:
        raise CharacterServiceError(f"Failed to rebuild prompt contract: {e}", 500) from e

    try:
        write_json(
            lora_dir / "register.json",
            {
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "source": str(src),
                "comfy_lora_name": comfy_name,
                "comfy_path": comfy_installed,
                "strength": strength,
                "trigger_word": trigger,
            },
        )
    except PermissionError:
        # Non-fatal — DB registration still proceeds
        pass

    # Stay in training until human lock; if already ready, keep ready (retrain track)
    if c.status == CharacterStatus.TRAINING:
        pass  # wait for lock
    elif c.status == CharacterStatus.BOOTSTRAP:
        c.status = CharacterStatus.TRAINING

    c.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "character": character_to_out(await get_character(db, character_id)),
        "lora_path": version.lora_path,
        "comfy_lora_name": comfy_name,
        "comfy_installed": comfy_installed,
        "trigger_word": trigger,
        "strength": strength,
        "message": (
            "LoRA registered. Restart or refresh Comfy if it was already running so it sees "
            f"{comfy_name}. Then lock the character and generate — stills will load this LoRA."
        ),
    }


async def lora_status(db: AsyncSession, character_id: str) -> dict[str, Any]:
    c = await get_character(db, character_id)
    version = _working_version(c)
    layout = get_layout()
    approved = list(
        (
            await db.execute(
                select(Asset)
                .where(Asset.character_id == character_id)
                .where(Asset.decision == "approved")
                .where(Asset.kind == "still")
            )
        )
        .scalars()
        .all()
    )

    ds_count = 0
    lora_file = None
    train_cfg = None
    comfy_lora = None
    if version:
        ds_dir = layout.dataset_dir(c.id, version.version_int)
        if ds_dir.is_dir():
            ds_count = len(
                [p for p in ds_dir.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
            )
        if version.lora_path:
            lp = layout.root / version.lora_path
            lora_file = lp.is_file()
        cfg_path = layout.lora_dir(c.id, version.version_int) / "train_config.json"
        if cfg_path.is_file():
            train_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        flux = (version.pipeline_params_json or {}).get("flux") or {}
        comfy_lora = flux.get("comfy_lora_name")

    n_approved = len(approved)
    coverage_keys = [
        "portrait",
        "casual_bedroom",
        "lingerie_set",
        "outdoor_day",
        "glamour",
        "mirror_selfie",
        "gym",
    ]
    coverage: dict[str, bool] = {k: False for k in coverage_keys}
    for a in approved:
        pos = (a.prompt_positive or "").lower()
        for k in coverage_keys:
            token = k.replace("_", " ")
            if k in pos or token in pos or k.split("_")[0] in pos:
                coverage[k] = True
    missing = [k for k, ok in coverage.items() if not ok]
    return {
        "character_id": character_id,
        "status": c.status,
        "approved_stills": n_approved,
        "dataset_images": ds_count,
        "trigger_word": version.trigger_word if version else None,
        "lora_path": version.lora_path if version else None,
        "lora_file_present": lora_file,
        "comfy_lora_name": comfy_lora,
        "train_config": train_cfg,
        "version_id": version.id if version else None,
        "version_int": version.version_int if version else None,
        "ready_for_dataset": n_approved >= MIN_IMAGES_HARD,
        "recommended_min": 12,
        "coverage": coverage,
        "coverage_missing": missing,
        "toolkit_ready": _toolkit_visible(),
    }


def _toolkit_visible() -> bool:
    from instantimpact_common.toolkit import resolve_toolkit_dir

    settings = get_settings()
    return resolve_toolkit_dir(settings.ai_toolkit_dir or None) is not None
