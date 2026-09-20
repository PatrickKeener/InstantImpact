"""Helpers for product reference images during still generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def resolve_product_image(data_dir: Path, item: dict[str, Any]) -> Path | None:
    raw = item.get("product_ref_path")
    if not raw:
        return None
    p = Path(str(raw))
    if not p.is_absolute():
        p = data_dir / str(raw).replace("\\", "/").lstrip("/")
    return p if p.is_file() else None


def paste_product_corner(base, product_path: Path, *, margin: int = 24, max_width_ratio: float = 0.32):
    """
    Composite product ref into the lower-right corner of a still (mock/demo path).
    Returns the modified image. Requires Pillow Image already open as `base`.
    """
    from PIL import Image

    product = Image.open(product_path).convert("RGBA")
    bw, bh = base.size
    target_w = max(64, int(bw * max_width_ratio))
    scale = target_w / max(product.width, 1)
    target_h = max(64, int(product.height * scale))
    if target_h > int(bh * 0.4):
        scale = (bh * 0.4) / max(product.height, 1)
        target_w = max(64, int(product.width * scale))
        target_h = max(64, int(product.height * scale))
    product = product.resize((target_w, target_h))
    canvas = base.convert("RGBA")
    x = bw - target_w - margin
    y = bh - target_h - margin
    # subtle panel behind product for readability on dark mock stills
    panel = Image.new("RGBA", (target_w + 16, target_h + 16), (255, 255, 255, 40))
    canvas.paste(panel, (x - 8, y - 8), panel)
    canvas.paste(product, (x, y), product)
    return canvas.convert("RGB")


def product_meta_from_item(item: dict[str, Any]) -> dict[str, Any]:
    if not item.get("product_id"):
        return {}
    return {
        "product_id": item.get("product_id"),
        "product_name": item.get("product_name"),
        "product_ref_path": item.get("product_ref_path"),
        "product_placement": item.get("product_placement"),
        "product_conditioning": "prompt",  # image IP-Adapter slot reserved for later
    }
