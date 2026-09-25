"""Still-vs-ref similarity for review sort.

Default score is a face-weighted perceptual hash plus a coarse color histogram
on the upper-center crop (where a portrait face usually sits). Optional
InsightFace embeddings are used when the package is installed. This is a
review aid, not a face-ID guarantee.
"""

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


def face_similarity(image_path: Path, ref_path: Path) -> float | None:
    """Likeness of the portrait face region, 0–1."""
    embedded = _insightface_similarity(image_path, ref_path)
    if embedded is not None:
        return embedded
    dhash = _dhash_similarity(image_path, ref_path)
    hist = _histogram_similarity(image_path, ref_path)
    if dhash is None and hist is None:
        return similarity_score(image_path, ref_path)
    if dhash is None:
        return hist
    if hist is None:
        return dhash
    return round(0.7 * dhash + 0.3 * hist, 4)


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
    preferred = [p for p in refs if p.name.startswith("face_")]
    pool = preferred or refs[:12]
    scores = [s for s in (face_similarity(image_path, r) for r in pool) if s is not None]
    return max(scores) if scores else None


def _face_crop_box(width: int, height: int) -> tuple[int, int, int, int]:
    left = int(width * 0.12)
    right = int(width * 0.88)
    top = int(height * 0.04)
    bottom = int(height * 0.72)
    if right <= left or bottom <= top:
        return 0, 0, width, height
    return left, top, right, bottom


def _open_face_gray(path: Path):
    from PIL import Image

    im = Image.open(path).convert("RGB")
    box = _face_crop_box(*im.size)
    return im.crop(box)


def _dhash_similarity(image_path: Path, ref_path: Path) -> float | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    hash_size = 16
    size = (hash_size + 1, hash_size)
    try:
        a = _open_face_gray(image_path).convert("L").resize(size, Image.Resampling.LANCZOS)
        b = _open_face_gray(ref_path).convert("L").resize(size, Image.Resampling.LANCZOS)
    except Exception:
        return None
    bits_a = _dhash_bits(list(a.tobytes()), hash_size)
    bits_b = _dhash_bits(list(b.tobytes()), hash_size)
    same = sum(x == y for x, y in zip(bits_a, bits_b, strict=True))
    return round(same / len(bits_a), 4)


def _dhash_bits(pixels: list[int], hash_size: int) -> list[bool]:
    bits: list[bool] = []
    row = hash_size + 1
    for y in range(hash_size):
        offset = y * row
        for x in range(hash_size):
            bits.append(pixels[offset + x] > pixels[offset + x + 1])
    return bits


def _histogram_similarity(image_path: Path, ref_path: Path) -> float | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        a = _open_face_gray(image_path).resize((64, 64), Image.Resampling.BOX)
        b = _open_face_gray(ref_path).resize((64, 64), Image.Resampling.BOX)
    except Exception:
        return None
    hist_a = a.histogram()
    hist_b = b.histogram()
    if not hist_a or len(hist_a) != len(hist_b):
        return None
    # Intersection over the larger histogram mass.
    inter = sum(min(x, y) for x, y in zip(hist_a, hist_b, strict=True))
    denom = max(sum(hist_a), sum(hist_b), 1)
    return round(inter / denom, 4)


def _insightface_similarity(image_path: Path, ref_path: Path) -> float | None:
    """Cosine similarity of the first detected face when insightface is present."""
    try:
        import numpy as np
    except Exception:
        return None
    try:
        app = _insightface_app()
        if app is None:
            return None
        img_a = np.asarray(_open_face_gray(image_path).convert("RGB"))[:, :, ::-1]
        img_b = np.asarray(_open_face_gray(ref_path).convert("RGB"))[:, :, ::-1]
        faces_a = app.get(img_a)
        faces_b = app.get(img_b)
        if not faces_a or not faces_b:
            return None
        va = np.asarray(faces_a[0].normed_embedding, dtype=np.float32)
        vb = np.asarray(faces_b[0].normed_embedding, dtype=np.float32)
        denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
        if denom <= 0:
            return None
        cosine = float(np.dot(va, vb) / denom)
        return round(max(0.0, min((cosine + 1.0) / 2.0, 1.0)), 4)
    except Exception:
        return None


_FACE_APP = None
_FACE_APP_FAILED = False


def _insightface_app():
    global _FACE_APP, _FACE_APP_FAILED
    if _FACE_APP_FAILED:
        return None
    if _FACE_APP is not None:
        return _FACE_APP
    try:
        from insightface.app import FaceAnalysis

        app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=-1, det_size=(640, 640))
        _FACE_APP = app
        return app
    except Exception:
        _FACE_APP_FAILED = True
        return None
