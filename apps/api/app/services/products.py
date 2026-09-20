"""Product library — packaging/product shots for ad-style stills."""

from __future__ import annotations

import io
import re
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Product
from app.services.storage import get_layout, relative_to_data, sha256_file
from instantimpact_prompts.product import PRODUCT_PLACEMENTS, normalize_placement

_ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp"}
_MAX_BYTES = 15 * 1024 * 1024


class ProductServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def product_to_out(p: Product) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "slug": p.slug,
        "description": p.description,
        "brand": p.brand,
        "primary_path": p.primary_path,
        "thumb_path": p.thumb_path,
        "sha256": p.sha256,
        "width": p.width,
        "height": p.height,
        "meta": p.meta_json or {},
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (s or "product")[:80]


async def _unique_slug(db: AsyncSession, base: str, *, exclude_id: str | None = None) -> str:
    candidate = base
    n = 2
    while True:
        q = await db.execute(select(Product).where(Product.slug == candidate))
        existing = q.scalar_one_or_none()
        if existing is None or (exclude_id and existing.id == exclude_id):
            return candidate
        candidate = f"{base}-{n}"
        n += 1


async def list_products(db: AsyncSession, limit: int = 100) -> list[dict]:
    rows = (
        await db.execute(select(Product).order_by(Product.created_at.desc()).limit(limit))
    ).scalars().all()
    return [product_to_out(p) for p in rows]


async def get_product(db: AsyncSession, product_id: str) -> Product:
    q = await db.execute(select(Product).where(Product.id == product_id))
    p = q.scalar_one_or_none()
    if not p:
        raise ProductServiceError("Product not found", 404)
    return p


async def create_product(
    db: AsyncSession,
    *,
    name: str,
    upload: UploadFile,
    description: str | None = None,
    brand: str | None = None,
) -> dict:
    from app.config import get_settings

    settings = get_settings()
    if not settings.enable_product_uploads:
        raise ProductServiceError("Product uploads are disabled (INSTANTIMPACT_ENABLE_PRODUCT_UPLOADS)")

    raw_name = (name or "").strip()
    if not raw_name:
        raise ProductServiceError("Product name is required")

    filename = upload.filename or "product.png"
    ext = Path(filename).suffix.lower()
    if ext == ".jpeg":
        ext = ".jpg"
    if ext not in _ALLOWED_EXT:
        raise ProductServiceError(f"Unsupported image type (use PNG/JPEG/WebP), got {ext or 'none'}")

    data = await upload.read()
    if not data:
        raise ProductServiceError("Empty upload")
    if len(data) > _MAX_BYTES:
        raise ProductServiceError("Product image too large (max 15 MB)")

    try:
        from PIL import Image
    except ImportError as e:
        raise ProductServiceError("Pillow is required for product uploads") from e

    try:
        im = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception as e:
        raise ProductServiceError(f"Could not decode image: {e}") from e

    product_id = str(uuid.uuid4())
    layout = get_layout()
    pdir = layout.product_dir(product_id)
    pdir.mkdir(parents=True, exist_ok=True)
    primary = pdir / f"primary{ext if ext != '.jpg' else '.jpg'}"
    # Normalize to PNG for consistent worker loading
    primary = pdir / "primary.png"
    im.save(primary, "PNG")
    thumb = pdir / "thumb.png"
    tw = 192
    th = max(1, int(192 * im.height / max(im.width, 1)))
    im.resize((tw, th)).save(thumb, "PNG")

    slug = await _unique_slug(db, _slugify(raw_name))
    product = Product(
        id=product_id,
        name=raw_name,
        slug=slug,
        description=(description or "").strip() or None,
        brand=(brand or "").strip() or None,
        primary_path=relative_to_data(primary),
        thumb_path=relative_to_data(thumb),
        sha256=sha256_file(primary),
        width=im.width,
        height=im.height,
        meta_json={
            "kind": "product_ref",
            "original_filename": filename,
            "placements": list(PRODUCT_PLACEMENTS.keys()),
        },
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product_to_out(product)


async def update_product(
    db: AsyncSession,
    product_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    brand: str | None = None,
) -> dict:
    p = await get_product(db, product_id)
    if name is not None:
        raw = name.strip()
        if not raw:
            raise ProductServiceError("Product name cannot be empty")
        p.name = raw
        p.slug = await _unique_slug(db, _slugify(raw), exclude_id=p.id)
    if description is not None:
        p.description = description.strip() or None
    if brand is not None:
        p.brand = brand.strip() or None
    await db.commit()
    await db.refresh(p)
    return product_to_out(p)


async def delete_product(db: AsyncSession, product_id: str) -> dict:
    p = await get_product(db, product_id)
    layout = get_layout()
    pdir = layout.product_dir(product_id)
    removed = 0
    if pdir.is_dir():
        for f in pdir.rglob("*"):
            if f.is_file():
                f.unlink(missing_ok=True)
                removed += 1
        try:
            pdir.rmdir()
        except OSError:
            pass
    await db.delete(p)
    await db.commit()
    return {"id": product_id, "deleted": True, "files_removed": removed}


def resolve_product_fields(product: Product, placement: str | None) -> dict:
    """Denormalize product into StillUnitRequest fields."""
    place = normalize_placement(placement)
    desc_parts = []
    if product.brand:
        desc_parts.append(f"brand {product.brand}")
    if product.description:
        desc_parts.append(product.description)
    return {
        "product_id": product.id,
        "product_name": product.name,
        "product_description": "; ".join(desc_parts) if desc_parts else None,
        "product_ref_path": product.primary_path,
        "product_placement": place,
    }
