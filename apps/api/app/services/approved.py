"""Approved sets: immutable copies + hash manifest + zip export."""

from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ApprovedSet, ApprovedSetItem, Asset
from app.services.jobs import JobServiceError
from app.services.storage import get_layout, sha256_file, write_json
from instantimpact_common.safety_lists import SYNTHETIC_DISCLOSURE_DEFAULT


def _set_to_out(aset: ApprovedSet, items: list[ApprovedSetItem] | None = None) -> dict[str, Any]:
    rows = items if items is not None else list(getattr(aset, "items", []) or [])
    return {
        "id": aset.id,
        "character_id": aset.character_id,
        "title": aset.title,
        "manifest_path": aset.manifest_path,
        "export_path": aset.export_path,
        "human_export_approved_at": aset.human_export_approved_at,
        "created_at": aset.created_at,
        "item_count": len(rows),
        "items": [
            {"asset_id": i.asset_id, "position": i.position, "path": None, "thumb_path": None}
            for i in sorted(rows, key=lambda x: x.position)
        ],
    }


async def list_sets(db: AsyncSession, character_id: str) -> list[dict[str, Any]]:
    rows = list(
        (
            await db.execute(
                select(ApprovedSet)
                .where(ApprovedSet.character_id == character_id)
                .order_by(ApprovedSet.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    out = []
    for aset in rows:
        items = list(
            (
                await db.execute(
                    select(ApprovedSetItem).where(ApprovedSetItem.set_id == aset.id)
                )
            )
            .scalars()
            .all()
        )
        out.append(_set_to_out(aset, items))
    return out


async def get_set(db: AsyncSession, set_id: str) -> tuple[ApprovedSet, list[ApprovedSetItem]]:
    q = await db.execute(select(ApprovedSet).where(ApprovedSet.id == set_id))
    aset = q.scalar_one_or_none()
    if not aset:
        raise JobServiceError("Approved set not found", 404)
    items = list(
        (await db.execute(select(ApprovedSetItem).where(ApprovedSetItem.set_id == set_id)))
        .scalars()
        .all()
    )
    return aset, items


async def create_set(
    db: AsyncSession,
    character_id: str,
    *,
    title: str,
    asset_ids: list[str],
) -> dict[str, Any]:
    if not asset_ids:
        raise JobServiceError("Select at least one asset")
    q = await db.execute(
        select(Asset).where(Asset.id.in_(asset_ids)).where(Asset.character_id == character_id)
    )
    assets = list(q.scalars().all())
    by_id = {a.id: a for a in assets}
    missing = [i for i in asset_ids if i not in by_id]
    if missing:
        raise JobServiceError(f"Unknown assets: {', '.join(missing[:8])}", 404)
    not_approved = [a.id for a in assets if a.decision != "approved"]
    if not_approved:
        raise JobServiceError("All assets in a set must be approved first")

    aset = ApprovedSet(character_id=character_id, title=title)
    db.add(aset)
    await db.flush()

    layout = get_layout()
    set_dir = layout.approved_set_dir(aset.id)
    files_dir = set_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    manifest_files: list[dict[str, Any]] = []
    ordered: list[ApprovedSetItem] = []
    for pos, aid in enumerate(asset_ids):
        asset = by_id[aid]
        src = layout.root / str(asset.path).replace("\\", "/")
        if not src.is_file():
            raise JobServiceError(f"Asset file missing on disk: {asset.path}", 400)
        ext = src.suffix.lower() or ".png"
        dest_name = f"{pos:03d}_{aid[:8]}{ext}"
        dest = files_dir / dest_name
        shutil.copy2(src, dest)
        digest = sha256_file(dest)
        disclosure = {
            "synthetic": True,
            "ai_generated": True,
            "age_appearance": "21+",
            "disclosure": SYNTHETIC_DISCLOSURE_DEFAULT,
            "asset_id": asset.id,
            "character_id": character_id,
            "seed": asset.seed,
            "sha256": digest,
        }
        sidecar = dest.with_suffix(dest.suffix + ".disclosure.json")
        if dest.suffix.lower() == ".png":
            sidecar = dest.with_suffix(".disclosure.json")
        write_json(sidecar, disclosure)
        item = ApprovedSetItem(set_id=aset.id, asset_id=asset.id, position=pos)
        db.add(item)
        ordered.append(item)
        manifest_files.append(
            {
                "file": dest_name,
                "disclosure": sidecar.name,
                "asset_id": asset.id,
                "sha256": digest,
                "seed": asset.seed,
            }
        )

    manifest = {
        "set_id": aset.id,
        "character_id": character_id,
        "title": title,
        "synthetic": True,
        "ai_generated": True,
        "age_appearance": "21+",
        "disclosure": SYNTHETIC_DISCLOSURE_DEFAULT,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": manifest_files,
    }
    manifest_path = set_dir / "manifest.json"
    write_json(manifest_path, manifest)
    aset.manifest_path = str(manifest_path.relative_to(layout.root)).replace("\\", "/")
    await db.commit()
    aset, items = await get_set(db, aset.id)
    return _set_to_out(aset, items)


async def export_set(
    db: AsyncSession,
    set_id: str,
    *,
    confirm_adult_synthetic: bool,
) -> dict[str, Any]:
    if not confirm_adult_synthetic:
        raise JobServiceError(
            "Export requires confirm_adult_synthetic=true "
            "(I confirm all assets depict a clearly adult synthetic persona)"
        )
    aset, items = await get_set(db, set_id)
    layout = get_layout()
    set_dir = layout.approved_set_dir(aset.id)
    files_dir = set_dir / "files"
    if not files_dir.is_dir():
        raise JobServiceError("Approved set files missing on disk", 400)

    # Verify hashes
    manifest_path = layout.root / (aset.manifest_path or "")
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for entry in manifest.get("files") or []:
            f = files_dir / entry["file"]
            if not f.is_file():
                raise JobServiceError(f"Missing file in set: {entry['file']}", 400)
            digest = sha256_file(f)
            if entry.get("sha256") and digest != entry["sha256"]:
                raise JobServiceError(f"Hash mismatch for {entry['file']} — set may be corrupted")

    exports = layout.exports_dir
    exports.mkdir(parents=True, exist_ok=True)
    zip_name = f"{aset.character_id[:8]}_{aset.id[:8]}.zip"
    zip_path = exports / zip_name
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in set_dir.rglob("*"):
            if p.is_file():
                zf.write(p, arcname=str(p.relative_to(set_dir)))

    aset.human_export_approved_at = datetime.now(timezone.utc)
    aset.export_path = str(zip_path.relative_to(layout.root)).replace("\\", "/")
    await db.commit()
    aset, items = await get_set(db, set_id)
    out = _set_to_out(aset, items)
    out["export_path"] = aset.export_path
    out["download"] = f"/api/system/media/{aset.export_path}"
    return out
