from instantimpact_prompts.ad_copy import render_ad_copy


def test_render_ad_copy_with_product_and_voice():
    out = render_ad_copy(
        character_name="Ruby",
        personality={"traits": ["warm", "confident"], "tone": "playful", "bio_short": "Soft glam muse."},
        speaking_style={"formality": "warm", "emoji_use": "light", "example_lines": ["Hey love."]},
        marketing_voice={
            "tagline": "Soft glam, no filter energy.",
            "audience": "everyday luxury fans",
            "cta_style": "playful",
            "value_props": ["feels effortless"],
            "words_to_use": ["glow", "soft"],
            "words_to_avoid": ["cheap"],
            "sample_ads": ["This is my reset ritual."],
            "hashtag_style": "branded",
            "sign_off": "xx Ruby",
        },
        product_name="Aurora Serum",
        product_brand="Aurora",
        product_description="frosted glass bottle",
        product_placement="holding",
        theme="glamour",
        count=3,
        seed=7,
    )
    assert out["engine"] == "template_v1"
    assert "Aurora Serum" in out["primary"] or "Aurora" in out["primary"]
    assert len(out["variants"]) == 3
    assert out["cta"]
    assert "cheap" not in out["primary"].lower()


def test_render_ad_copy_without_product():
    out = render_ad_copy(
        character_name="Aria",
        marketing_voice={"cta_style": "direct", "hashtag_style": "none"},
        theme="portrait",
        count=1,
        seed=1,
    )
    assert out["primary"]
    assert out["product_name"] is None
