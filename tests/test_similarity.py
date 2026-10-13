from pathlib import Path

from PIL import Image

from instantimpact_common.similarity import (
    best_ref_similarity,
    crop_face_image,
    face_similarity,
    similarity_score,
)


def test_identical_images_score_one(tmp_path: Path):
    p = tmp_path / "a.png"
    Image.new("RGB", (32, 32), color=(200, 40, 40)).save(p)
    assert similarity_score(p, p) == 1.0


def test_different_images_lower_score(tmp_path: Path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    img_a = Image.new("RGB", (32, 32))
    img_b = Image.new("RGB", (32, 32))
    px_a = img_a.load()
    px_b = img_b.load()
    for y in range(32):
        for x in range(32):
            px_a[x, y] = (255 if (x // 4 + y // 4) % 2 == 0 else 0,) * 3
            px_b[x, y] = (int(255 * x / 31), int(255 * y / 31), 80)
    img_a.save(a)
    img_b.save(b)
    score = similarity_score(a, b)
    assert score is not None
    assert score < 0.9


def test_face_similarity_identical_is_one(tmp_path: Path):
    p = tmp_path / "face.png"
    Image.new("RGB", (128, 160), color=(180, 120, 90)).save(p)
    assert face_similarity(p, p) == 1.0


def test_best_ref_prefers_face_primary(tmp_path: Path):
    still = tmp_path / "still.png"
    refs = tmp_path / "refs"
    refs.mkdir()
    Image.new("RGB", (64, 80), color=(20, 20, 200)).save(still)
    Image.new("RGB", (64, 80), color=(20, 20, 200)).save(refs / "face_primary.png")
    Image.new("RGB", (64, 80), color=(200, 20, 20)).save(refs / "body_front.png")
    score = best_ref_similarity(still, refs)
    assert score is not None
    assert score > 0.9


def test_crop_face_image_uses_upper_center_box(tmp_path: Path):
    src = tmp_path / "full.png"
    dest = tmp_path / "face.png"
    Image.new("RGB", (400, 500), color=(30, 30, 40)).save(src)
    crop_face_image(src, dest)
    cropped = Image.open(dest)
    full = Image.open(src)
    assert cropped.size[0] < full.size[0]
    assert cropped.size[1] < full.size[1]
    assert dest.is_file()
