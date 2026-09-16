from pathlib import Path

from PIL import Image

from instantimpact_common.similarity import similarity_score


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
