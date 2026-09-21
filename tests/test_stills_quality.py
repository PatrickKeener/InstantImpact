from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "worker"))

from worker.tasks.stills import _ensure_adult_prompt, _size_for_aspect


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
