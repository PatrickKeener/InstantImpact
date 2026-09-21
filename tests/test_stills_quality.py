from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "worker"))

from worker.tasks.stills import _ensure_adult_prompt, _hires_size, _size_for_aspect


def test_aspect_ratio_wins_over_legacy_default_dimensions():
    legacy_flux = {"width": 1024, "height": 1280}
    assert _size_for_aspect("1:1", legacy_flux) == (1024, 1024)
    assert _size_for_aspect("9:16", legacy_flux) == (768, 1344)
    assert _size_for_aspect("16:9", legacy_flux) == (1344, 768)


def test_explicit_dimension_override_wins():
    flux = {
        "override_dimensions": True,
        "width": 832,
        "height": 1216,
    }
    assert _size_for_aspect("1:1", flux) == (832, 1216)


def test_adult_fallback_uses_character_age_floor():
    prompt = _ensure_adult_prompt("photorealistic portrait", age_appearance_min=32)
    assert "32+ appearance" in prompt
    assert "25 years old" not in prompt


def test_adult_fallback_does_not_duplicate_contract_tokens():
    prompt = "clearly adult woman, 21+ appearance, photorealistic portrait"
    assert _ensure_adult_prompt(prompt, age_appearance_min=32) == prompt


def test_hires_size_scales_every_aspect_preset():
    for width, height in (1024, 1024), (1024, 1280), (960, 1280), (768, 1344), (1344, 768):
        hi_w, hi_h = _hires_size(width, height, 1.5)
        assert (hi_w, hi_h) == (int(width * 1.5), int(height * 1.5))


def test_hires_size_snaps_fractional_scales_to_multiples_of_16():
    hi_w, hi_h = _hires_size(1024, 1280, 1.3)
    assert hi_w % 16 == 0 and hi_h % 16 == 0


def test_hires_size_clamps_runaway_scale():
    assert _hires_size(1024, 1280, 8.0) == (2048, 2560)
    assert _hires_size(1024, 1280, 0.25) == (1024, 1280)
