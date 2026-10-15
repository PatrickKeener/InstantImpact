"""Bootstrap identity lock: pin a seed still, then generate more of that person.

Flux txt2img resamples a new face on every random seed. Until a character LoRA
exists, lock one still: the full frame is copied to refs/identity_source.png
(img2img latent) and a head crop to refs/face_primary.png (PuLID + scoring).
Expand jobs encode identity_source at mid denoise with pose/outfit variations.
"""

from __future__ import annotations

import random
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.db.models import Asset, CharacterVersion
from app.services.characters import (
    CharacterServiceError,
    _working_version,
    get_character,
)
from app.services.storage import get_layout, relative_to_data, resolve_under_root
from instantimpact_common.schemas import StillUnitRequest

# Portrait-adjacent first so same-seed expansions keep the face. Later entries
# add the coverage themes LoRA training wants (bedroom, glamour, outdoor, …).
IDENTITY_VARIATIONS: list[dict[str, str]] = [
    {
        "theme": "portrait",
        "outfit_hint": "simple black tank top",
        "pose_hint": "looking at the camera",
        "extra_prompt": "tight head-and-shoulders crop, even window light",
    },
    {
        "theme": "portrait",
        "outfit_hint": "soft white blouse",
        "pose_hint": "three-quarter view, looking slightly off camera",
        "extra_prompt": "chest-up crop, soft side light",
    },
    {
        "theme": "portrait",
        "outfit_hint": "crew-neck sweater",
        "pose_hint": "soft closed-mouth smile, chin slightly down",
        "extra_prompt": "beauty lighting, sharp eyes",
    },
    {
        "theme": "portrait",
        "outfit_hint": "black tank top",
        "pose_hint": "looking over one shoulder",
        "extra_prompt": "three-quarter crop, hair catching backlight",
    },
    {
        "theme": "glamour",
        "outfit_hint": "black evening dress",
        "pose_hint": "confident editorial stance, one hand near collarbone",
        "extra_prompt": "studio rim light, waist-up",
    },
    {
        "theme": "glamour",
        "outfit_hint": "silk slip dress",
        "pose_hint": "seated, legs to the side, looking at camera",
        "extra_prompt": "soft directional studio lighting",
    },
    {
        "theme": "casual_bedroom",
        "outfit_hint": "oversized tee",
        "pose_hint": "sitting on the edge of the bed",
        "extra_prompt": "candid lifestyle crop, daylight through window",
    },
    {
        "theme": "casual_bedroom",
        "outfit_hint": "camisole and shorts",
        "pose_hint": "standing by a window, relaxed",
        "extra_prompt": "natural backlight through curtains",
    },
    {
        "theme": "mirror_selfie",
        "outfit_hint": "casual loungewear",
        "pose_hint": "phone in hand, looking into the mirror",
        "extra_prompt": "bathroom mirror, authentic smartphone photo",
    },
    {
        "theme": "lingerie_set",
        "outfit_hint": "matching lingerie set",
        "pose_hint": "standing, weight on one hip",
        "extra_prompt": "tasteful editorial, three-quarter length",
    },
    {
        "theme": "outdoor_day",
        "outfit_hint": "sundress",
        "pose_hint": "walking toward camera",
        "extra_prompt": "daylight documentary, environmental portrait",
    },
    {
        "theme": "gym",
        "outfit_hint": "fitted athletic wear",
        "pose_hint": "standing, hands on hips, looking at camera",
        "extra_prompt": "available light sports portrait, gym background",
    },
]

_FACE_PRIMARY_NAMES = ("face_primary.png", "face_primary.jpg", "face_primary.webp")
IDENTITY_SOURCE_NAME = "identity_source.png"

# Product gates on face_similarity vs face_primary. None (imports / unscored) passes.
LIKENESS_APPROVE_MIN = 0.45
LIKENESS_TRAIN_MIN = 0.55
LIKENESS_NEAR_DUP = 0.97
_FRAMING_JITTER = (
    "slightly tighter crop",
    "camera a little lower",
    "camera a little higher",
    "half-step to camera left",
)


def read_lock(version: CharacterVersion | None) -> dict[str, Any] | None:
    if version is None:
        return None
    raw = (version.pipeline_params_json or {}).get("identity_lock")
    if not isinstance(raw, dict):
        return None
    asset_id = str(raw.get("asset_id") or "").strip()
    if not asset_id:
        return None
    seed = raw.get("seed")
    try:
        seed_int = int(seed) if seed is not None else None
    except (TypeError, ValueError):
        seed_int = None
    face_ref = str(raw.get("face_ref") or "").strip() or None
    identity_source = str(raw.get("identity_source") or "").strip() or None
    return {
        "asset_id": asset_id,
        "seed": seed_int,
        "face_ref": face_ref,
        "identity_source": identity_source,
        "locked_at": raw.get("locked_at"),
    }


def variation_units(
    *,
    count: int,
    aspect_ratio: str = "4:5",
    seed: int | None = None,
) -> list[StillUnitRequest]:
    if count < 1:
        raise CharacterServiceError("Need at least one still")
    units: list[StillUnitRequest] = []
    n = len(IDENTITY_VARIATIONS)
    for i in range(count):
        spec = IDENTITY_VARIATIONS[i % n]
        extra = spec.get("extra_prompt") or ""
        if i >= n:
            jitter = _FRAMING_JITTER[i % len(_FRAMING_JITTER)]
            extra = f"{extra}, {jitter}" if extra else jitter
        units.append(
            StillUnitRequest(
                item_index=i,
                seed=seed,
                theme=spec["theme"],
                outfit_hint=spec.get("outfit_hint"),
                pose_hint=spec.get("pose_hint"),
                extra_prompt=extra or None,
                aspect_ratio=aspect_ratio,
            )
        )
    return units


def copy_asset_to_face_primary(asset: Asset, refs_dir: Path) -> Path:
    """Write identity_source.png (full still) and face_primary.png (head crop)."""
    src = _asset_file(asset)
    if src is None:
        raise CharacterServiceError("Still file is missing on disk", 400)
    refs_dir.mkdir(parents=True, exist_ok=True)
    dest = refs_dir / "face_primary.png"
    identity_source = refs_dir / IDENTITY_SOURCE_NAME
    for stale in _FACE_PRIMARY_NAMES:
        path = refs_dir / stale
        if path != dest and path.is_file():
            path.unlink()
    _write_png(src, identity_source)
    try:
        from instantimpact_common.similarity import crop_face_image

        crop_face_image(identity_source, dest)
    except Exception:
        shutil.copy2(identity_source, dest)
    return dest


def _write_png(src: Path, dest: Path) -> None:
    if src.suffix.lower() == ".png":
        shutil.copy2(src, dest)
        return
    try:
        from PIL import Image
    except ImportError as e:
        raise CharacterServiceError("Pillow is required to lock a non-PNG still") from e
    with Image.open(src) as im:
        im.convert("RGB").save(dest, "PNG")


def likeness_for_asset(asset: Asset, refs_dir: Path | None) -> float | None:
    """Live face_primary score, else the stored consistency_score."""
    src = _asset_file(asset)
    live = _score_against_primary(src, refs_dir) if src else None
    if live is not None:
        return live
    return stored_likeness_for_asset(asset)


def stored_likeness_for_asset(asset: Asset) -> float | None:
    """Return the score recorded when the still was generated, without image analysis."""
    raw = asset.consistency_score
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _score_against_primary(image_path: Path, refs_dir: Path | None) -> float | None:
    if not refs_dir or not refs_dir.is_dir():
        return None
    primary = None
    for name in _FACE_PRIMARY_NAMES:
        candidate = refs_dir / name
        if candidate.is_file():
            primary = candidate
            break
    if primary is None:
        return None
    try:
        from instantimpact_common.similarity import face_similarity

        return face_similarity(image_path, primary)
    except Exception:
        return None


def _asset_file(asset: Asset) -> Path | None:
    if not asset.path:
        return None
    path = resolve_under_root(asset.path)
    return path if path is not None and path.is_file() else None


def _write_lock(version: CharacterVersion, payload: dict[str, Any]) -> dict[str, Any]:
    params = dict(version.pipeline_params_json or {})
    params["identity_lock"] = payload
    version.pipeline_params_json = params
    flag_modified(version, "pipeline_params_json")
    return payload


async def apply_identity_lock(
    db: AsyncSession,
    character_id: str,
    asset: Asset,
    *,
    approve: bool = True,
) -> dict[str, Any]:
    """Pin this still as the bootstrap face. Does not commit."""
    if asset.character_id != character_id:
        raise CharacterServiceError("Asset does not belong to this character", 404)
    c = await get_character(db, character_id)
    version = _working_version(c)
    if version is None:
        raise CharacterServiceError("Character has no version")

    layout = get_layout()
    refs_dir = layout.refs_dir(c.id, version.version_int)
    dest = copy_asset_to_face_primary(asset, refs_dir)
    version.ref_pack_path = relative_to_data(refs_dir)
    identity_source = refs_dir / IDENTITY_SOURCE_NAME
    source_ref = identity_source if identity_source.is_file() else dest

    seed = asset.seed
    if seed is None:
        seed = random.randint(1, 2**31 - 1)
    if approve and asset.decision != "approved":
        asset.decision = "approved"

    lock = {
        "asset_id": asset.id,
        "seed": int(seed),
        "face_ref": relative_to_data(dest),
        "identity_source": relative_to_data(source_ref),
        "locked_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_lock(version, lock)
    c.updated_at = datetime.now(timezone.utc)
    return lock


async def maybe_autolock(db: AsyncSession, asset: Asset) -> dict[str, Any] | None:
    """First approved still becomes the identity lock if none is set."""
    if asset.decision != "approved":
        return None
    c = await get_character(db, asset.character_id)
    version = _working_version(c)
    if read_lock(version):
        return None
    try:
        return await apply_identity_lock(db, asset.character_id, asset, approve=False)
    except CharacterServiceError:
        return None


async def lock_from_asset_id(
    db: AsyncSession,
    character_id: str,
    asset_id: str,
) -> dict[str, Any]:
    q = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = q.scalar_one_or_none()
    if asset is None:
        raise CharacterServiceError("Asset not found", 404)
    lock = await apply_identity_lock(db, character_id, asset, approve=True)
    await db.commit()
    return lock


async def unlock_identity(db: AsyncSession, character_id: str) -> dict[str, Any]:
    c = await get_character(db, character_id)
    version = _working_version(c)
    if version is None:
        raise CharacterServiceError("Character has no version")
    params = dict(version.pipeline_params_json or {})
    params.pop("identity_lock", None)
    version.pipeline_params_json = params
    flag_modified(version, "pipeline_params_json")
    c.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"character_id": character_id, "identity_lock": None}
