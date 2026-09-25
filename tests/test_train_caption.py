from types import SimpleNamespace

from instantimpact_prompts.train_caption import caption_from_asset, training_caption


def test_training_caption_describes_variation_not_identity():
    cap = training_caption(
        trigger="sks_aria_v1",
        theme="portrait",
        outfit_hint="oversized tee",
        pose_hint="looking at camera",
        location_hint="sunlit loft",
    )
    assert cap.startswith("sks_aria_v1")
    assert "adult woman" in cap
    assert "wearing oversized tee" in cap
    assert "looking at camera" in cap
    assert "sunlit loft" in cap
    assert "auburn" not in cap
    assert "green eyes" not in cap


def test_training_caption_keeps_nude_state_without_wearing_prefix():
    cap = training_caption(trigger="sks_aria_v1", theme="glamour", outfit_hint="topless")
    assert "wearing topless" not in cap
    assert "topless" in cap


def test_caption_from_asset_uses_meta_theme():
    asset = SimpleNamespace(
        prompt_positive="photorealistic photograph, clearly adult woman, auburn hair",
        meta_json={"theme": "casual_bedroom", "outfit_hint": "knit cardigan"},
    )
    cap = caption_from_asset(trigger="sks_aria_v1", asset=asset)
    assert "casual bedroom" in cap
    assert "knit cardigan" in cap
    assert "auburn" not in cap
