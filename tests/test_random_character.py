from app.services.random_character import build_random_character_create


def test_random_character_is_adult_and_attested():
    p = build_random_character_create(seed=42, auto_attest=True)
    assert p.age_appearance_min >= 21
    assert p.synthetic_confirmed is True
    assert p.not_real_person_attested is True
    assert p.attestation_text
    assert p.display_name
    assert p.appearance.hair_color
    assert p.appearance.eye_color
    assert len(p.personality.traits) >= 1


def test_random_character_reproducible_with_seed():
    a = build_random_character_create(seed=7, auto_attest=True)
    b = build_random_character_create(seed=7, auto_attest=True)
    assert a.display_name == b.display_name
    assert a.appearance.hair_color == b.appearance.hair_color
    assert a.appearance.eye_color == b.appearance.eye_color


def test_random_without_attest():
    p = build_random_character_create(seed=1, auto_attest=False)
    assert p.synthetic_confirmed is False
    assert p.not_real_person_attested is False


def test_random_character_photoreal_nude_language():
    p = build_random_character_create(seed=11, auto_attest=False)
    notes = (p.appearance.freeform_notes or "").lower()
    assert "photorealistic" in notes
    assert "nude" in notes and "naked" in notes
    assert "adult" in notes
    assert any(w in notes for w in ("breast", "breasts", "hourglass", "thick", "figure"))
    allowed = {x.lower() for x in p.boundaries.content_allowed}
    assert "nude" in allowed and "naked" in allowed
    assert p.appearance.body_type
    feats = " ".join(p.appearance.distinguishing_features).lower()
    assert "breast" in feats
