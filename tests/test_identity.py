"""Bootstrap identity lock: same-seed variations for LoRA seed collection."""

from app.services.identity import IDENTITY_VARIATIONS, variation_units


def test_variation_units_share_seed_and_change_pose():
    units = variation_units(count=8, seed=42, aspect_ratio="4:5")
    assert [u.seed for u in units] == [42] * 8
    assert len({u.pose_hint for u in units}) >= 6
    assert len({(u.theme, u.outfit_hint, u.pose_hint) for u in units}) == 8
    assert all(u.aspect_ratio == "4:5" for u in units)


def test_variation_units_cycle_without_duplicate_prompts():
    n = len(IDENTITY_VARIATIONS) + 3
    units = variation_units(count=n, seed=7)
    extras = [u.extra_prompt or "" for u in units]
    assert extras[0] != extras[len(IDENTITY_VARIATIONS)]
    assert all(u.seed == 7 for u in units)


def test_variation_units_without_seed_leave_seeds_unset():
    units = variation_units(count=4)
    assert all(u.seed is None for u in units)
    assert len({u.pose_hint for u in units}) >= 3
