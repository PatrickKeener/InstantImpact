from instantimpact_common.safety import scan_text, validate_for_enqueue


def test_blocks_underage_language():
    r = scan_text("cute teen model")
    assert not r.ok
    assert r.matched_category == "underage_language"


def test_allows_adult_theme():
    r = scan_text("casual bedroom soft daylight adult woman")
    assert r.ok


def test_enqueue_requires_synthetic():
    r = validate_for_enqueue(
        job_type="still_batch",
        character_status="bootstrap",
        synthetic_confirmed=False,
        age_appearance_min=21,
        not_real_person_attested=True,
    )
    assert not r.ok


def test_still_batch_blocks_draft():
    r = validate_for_enqueue(
        job_type="still_batch",
        character_status="draft",
        synthetic_confirmed=True,
        age_appearance_min=21,
        not_real_person_attested=True,
    )
    assert not r.ok
