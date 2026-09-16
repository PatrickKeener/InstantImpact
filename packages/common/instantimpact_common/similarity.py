"""Optional cheap still-vs-ref similarity (average hash). Not a face ID score."""

from __future__ import annotations

from pathlib import Path


def average_hash_bits(path: Path, hash_size: int = 8) -> list[bool] | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        im = Image.open(path).convert("L").resize((hash_size, hash_size))
    except Exception:
        return None
    pixels = list(im.tobytes())
    if not pixels:
        return None
    avg = sum(pixels) / len(pixels)
    return [p >= avg for p in pixels]


def similarity_score(image_path: Path, ref_path: Path) -> float | None:
    a = average_hash_bits(image_path)
    b = average_hash_bits(ref_path)
    if not a or not b or len(a) != len(b):
        return None
    same = sum(x == y for x, y in zip(a, b, strict=True))
    return round(same / len(a), 4)


def best_ref_similarity(image_path: Path, refs_dir: Path | None) -> float | None:
    if not refs_dir or not refs_dir.is_dir():
        return None
    refs = [
        p
        for p in refs_dir.iterdir()
        if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    ]
    if not refs:
        return None
    scores = [s for s in (similarity_score(image_path, r) for r in refs[:12]) if s is not None]
    return max(scores) if scores else None
