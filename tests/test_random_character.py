from app.services.random_character import (
    _BODIES,
    _PALETTES,
    build_random_character_create,
)


def test_random_character_is_adult_and_attested():
    p = build_random_character_create(seed=42, auto_attest=True)
    assert p.age_appearance_min >= 21
    assert p.synthetic_confirmed is True
    assert p.not_real_person_attested is True
    assert p.attestation_text
    assert p.display_name
    assert " " in p.display_name
    assert p.appearance.hair_color
    assert p.appearance.eye_color
    assert len(p.personality.traits) >= 1


def test_random_character_reproducible_with_seed():
    a = build_random_character_create(seed=7, auto_attest=True)
    b = build_random_character_create(seed=7, auto_attest=True)
    assert a.display_name == b.display_name
    assert a.appearance.hair_color == b.appearance.hair_color
    assert a.appearance.eye_color == b.appearance.eye_color
    assert a.appearance.ethnicity_hint == b.appearance.ethnicity_hint
    assert a.appearance.body_type == b.appearance.body_type


def test_random_without_attest():
    p = build_random_character_create(seed=1, auto_attest=False)
    assert p.synthetic_confirmed is False
    assert p.not_real_person_attested is False


def test_random_character_photoreal_profile_is_concise():
    p = build_random_character_create(seed=11, auto_attest=False)
    notes = (p.appearance.freeform_notes or "").lower()
    assert "photorealistic" in notes
    assert "adult" in notes
    assert p.appearance.hair_color.lower() not in notes
    assert p.appearance.eye_color.lower() not in notes
    allowed = {x.lower() for x in p.boundaries.content_allowed}
    assert "nude" in allowed and "naked" in allowed
    assert p.appearance.body_type
    feats = " ".join(p.appearance.distinguishing_features).lower()
    assert "breast" in feats
    assert "breast" not in p.appearance.body_type.lower()


def test_random_character_palettes_stay_coherent():
    for seed in range(60):
        p = build_random_character_create(seed=seed, auto_attest=False)
        palette = next(x for x in _PALETTES if x["ethnicity"] == p.appearance.ethnicity_hint)
        assert p.appearance.ethnicity_hint == palette["ethnicity"]
        assert p.appearance.skin_tone in palette["skin"]
        assert p.appearance.hair_color in palette["hair"]
        assert p.appearance.eye_color in palette["eyes"]
        body = next(x for x in _BODIES if x["body_type"] == p.appearance.body_type)
        assert p.appearance.height_hint in body["heights"]
        feats = " ".join(p.appearance.distinguishing_features)
        assert any(b in feats for b in body["breasts"])
        if "petite adult frame" in p.appearance.body_type:
            assert "petite" in (p.appearance.height_hint or "")
        if "tall lean" in p.appearance.body_type:
            assert "tall" in (p.appearance.height_hint or "")


def test_random_character_names_one_ancestry_not_mixed():
    for seed in range(30):
        p = build_random_character_create(seed=seed, auto_attest=False)
        eth = (p.appearance.ethnicity_hint or "").lower()
        assert "mixed heritage" not in eth
        assert "woman" in eth
        assert "facial structure" in eth


def test_random_character_does_not_force_nude_wardrobe_every_time():
    nudeish = 0
    for seed in range(40):
        p = build_random_character_create(seed=seed, auto_attest=False)
        joined = " ".join(p.appearance.typical_wardrobe).lower()
        if "nude" in joined or "topless" in joined:
            nudeish += 1
    assert 0 < nudeish < 28
