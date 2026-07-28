from instantimpact_common.schemas import AppearanceProfile, BoundariesProfile
from instantimpact_prompts.contract import build_prompt_contract
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
