from instantimpact_common.schemas import AppearanceProfile, BoundariesProfile
from instantimpact_prompts.contract import build_prompt_contract
from instantimpact_prompts.product import product_prompt_fragment
from instantimpact_prompts.render_flux import render_flux_prompts


def test_render_includes_trigger_and_adult_tokens():
    contract = build_prompt_contract(
        appearance=AppearanceProfile(
            hair_color="auburn",
            hair_style="waves",
            eye_color="green",
            body_type="athletic",
        ),
        boundaries=BoundariesProfile(hard_bans=["violence"]),
        trigger_word="sks_aria_v1",
    )
    pos, neg = render_flux_prompts(contract, theme="casual_bedroom", outfit_hint="oversized tee")
    assert "sks_aria_v1" in pos
    assert "21+" in pos or "adult" in pos.lower()
    assert "photorealistic" in pos.lower() or "photograph" in pos.lower()
    assert "violence" in neg
    assert "child" in neg
    assert "cartoon" in neg or "anime" in neg
    assert "deformed nipples" in neg
    assert "natural nipples" in pos


def test_render_includes_product_placement():
    contract = build_prompt_contract(
        appearance=AppearanceProfile(hair_color="blonde"),
        boundaries=BoundariesProfile(),
        trigger_word="sks_ad_v1",
    )
    pos, _ = render_flux_prompts(
        contract,
        theme="glamour",
        product_name="Aurora Serum",
        product_description="frosted glass bottle",
        product_placement="holding",
    )
    assert "Aurora Serum" in pos
    assert "frosted glass bottle" in pos
    assert "product" in pos.lower()


def test_product_prompt_fragment_defaults():
    assert product_prompt_fragment(name=None) is None
    frag = product_prompt_fragment(name="Vial X", placement="featured")
    assert frag is not None
    assert "Vial X" in frag
    assert "advertisement" in frag.lower() or "hero" in frag.lower()
