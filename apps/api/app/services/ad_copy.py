"""Generate and attach marketing ad copy from a character's voice."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Asset, JobItem
from app.schemas.characters import AdCopyRequest, AssetCaptionSaveRequest
from app.services import characters as char_svc
from app.services import products as product_svc
from instantimpact_common.safety import scan_text
from instantimpact_prompts.ad_copy import render_ad_copy


class AdCopyServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _version_for_voice(c) -> Any:
    if c.locked_version_id:
        v = next((x for x in c.versions if x.id == c.locked_version_id), None)
        if v:
            return v
    return char_svc._working_version(c)


async def _hints_from_asset(db: AsyncSession, asset_id: str, character_id: str) -> dict[str, Any]:
    q = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = q.scalar_one_or_none()
    if not asset or asset.character_id != character_id:
        raise AdCopyServiceError("Asset not found", 404)
    req: dict[str, Any] = {}
    if asset.job_item_id:
        iq = await db.execute(select(JobItem).where(JobItem.id == asset.job_item_id))
        item = iq.scalar_one_or_none()
        if item:
            req = item.request_json or {}
    meta = asset.meta_json or {}
    return {
        "theme": req.get("theme") or meta.get("theme"),
        "product_id": req.get("product_id") or meta.get("product_id"),
        "product_name": req.get("product_name") or meta.get("product_name"),
        "product_description": req.get("product_description"),
        "product_placement": req.get("product_placement") or meta.get("product_placement"),
        "product_ref_path": req.get("product_ref_path") or meta.get("product_ref_path"),
    }


async def generate_ad_copy(db: AsyncSession, character_id: str, payload: AdCopyRequest) -> dict:
    c = await char_svc.get_character(db, character_id)
    version = _version_for_voice(c)
    if not version:
        raise AdCopyServiceError("Character has no version", 400)

    theme = payload.theme
    product_id = payload.product_id
    product_name = None
    product_brand = None
    product_description = None
    product_placement = payload.product_placement
    product_ref_path = None

    if payload.asset_id:
        hints = await _hints_from_asset(db, payload.asset_id, character_id)
        theme = theme or hints.get("theme")
        product_id = product_id or hints.get("product_id")
        product_name = hints.get("product_name")
        product_description = hints.get("product_description")
        product_placement = product_placement or hints.get("product_placement")
        product_ref_path = hints.get("product_ref_path")

    if product_id:
        try:
            p = await product_svc.get_product(db, product_id)
        except product_svc.ProductServiceError as e:
            raise AdCopyServiceError(e.message, e.status_code) from e
        fields = product_svc.resolve_product_fields(p, product_placement)
        product_name = fields["product_name"]
        product_description = fields["product_description"]
        product_placement = fields["product_placement"]
        product_ref_path = fields["product_ref_path"]
        product_brand = p.brand

    result = render_ad_copy(
        character_name=c.display_name,
        personality=version.personality_json or {},
        speaking_style=version.speaking_style_json or {},
        marketing_voice=version.marketing_voice_json or {},
        product_name=product_name,
        product_brand=product_brand,
        product_description=product_description,
        product_placement=product_placement,
        theme=theme,
        count=payload.count,
        seed=payload.seed,
    )

    texts = [result["primary"], result["short"], result["cta"]]
    texts.extend(v["caption"] for v in result["variants"])
    for t in texts:
        scan = scan_text(t)
        if not scan.ok:
            raise AdCopyServiceError("; ".join(scan.reasons))

    result["product_id"] = product_id
    result["product_ref_path"] = product_ref_path
    result["theme"] = theme
    return result


async def save_asset_caption(
    db: AsyncSession,
    character_id: str,
    asset_id: str,
    payload: AssetCaptionSaveRequest,
) -> dict:
    q = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = q.scalar_one_or_none()
    if not asset or asset.character_id != character_id:
        raise AdCopyServiceError("Asset not found", 404)

    scan = scan_text(payload.caption)
    if not scan.ok:
        raise AdCopyServiceError("; ".join(scan.reasons))
    if payload.short:
        scan2 = scan_text(payload.short)
        if not scan2.ok:
            raise AdCopyServiceError("; ".join(scan2.reasons))

    meta = dict(asset.meta_json or {})
    meta["marketing_caption"] = payload.caption.strip()
    if payload.short:
        meta["marketing_caption_short"] = payload.short.strip()
    if payload.cta:
        meta["marketing_cta"] = payload.cta.strip()
    if payload.product_id:
        meta["product_id"] = payload.product_id
    meta["marketing_caption_saved_at"] = datetime.now(timezone.utc).isoformat()
    asset.meta_json = meta
    await db.commit()
    await db.refresh(asset)
    return {
        "id": asset.id,
        "character_id": asset.character_id,
        "caption": meta.get("marketing_caption"),
        "short": meta.get("marketing_caption_short"),
        "cta": meta.get("marketing_cta"),
        "meta": meta,
    }
