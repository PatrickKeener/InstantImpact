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
    assert "natural nipples" not in pos


def test_anatomy_detail_only_used_for_revealing_shots():
    contract = build_prompt_contract(
        appearance=AppearanceProfile(hair_color="auburn"),
        boundaries=BoundariesProfile(),
        trigger_word="sks_aria_v1",
    )
    clothed, _ = render_flux_prompts(contract, theme="outdoor_day", outfit_hint="denim jacket")
    revealing, _ = render_flux_prompts(
        contract, theme="outdoor_day", outfit_hint="naked with see-through dress"
    )
    assert "natural nipples" not in clothed
    assert "natural nipples" in revealing


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


def test_shot_intent_outranks_character_defaults():
    contract = build_prompt_contract(
        appearance=AppearanceProfile(
            hair_color="auburn",
            style_keywords=["glamour photography", "soft studio light", "natural window light"],
            typical_wardrobe=["silk slip", "barely-there lingerie"],
            freeform_notes="works nude and naked as well as clothed, tasteful erotic photography",
        ),
        boundaries=BoundariesProfile(),
        trigger_word="sks_aria_v1",
    )
    pos, _ = render_flux_prompts(
        contract, theme="outdoor_day", outfit_hint="naked with see through dress"
    )
    # Character wardrobe is replaced, not merged, when the shot names an outfit
    assert "silk slip" not in pos
    assert "naked with see through dress" in pos
    # Indoor lighting defaults must not fight an outdoor scene
    assert "studio light" not in pos
    assert "window light" not in pos
    # The "as well as clothed" hedge would undo an explicit nude outfit
    assert "clothed" not in pos
    # Scene and outfit land ahead of the character's style defaults
    assert pos.index("clearly outdoors") < pos.index("glamour photography")
    assert pos.index("naked with see through dress") < pos.index("glamour photography")
    assert pos.index("clearly outdoors") < pos.index("auburn")


def test_clip_l_keeps_shot_and_drops_character_quality_stack():
    from instantimpact_prompts.render_flux import render_flux_encoder_prompts

    contract = build_prompt_contract(
        appearance=AppearanceProfile(
            hair_color="auburn",
            typical_wardrobe=["silk slip"],
            freeform_notes="tasteful erotic photography",
        ),
        boundaries=BoundariesProfile(),
        trigger_word="sks_aria_v1",
    )
    clip_l, t5, _ = render_flux_encoder_prompts(
        contract,
        theme="outdoor_day",
        outfit_hint="naked with see through dress",
        location_hint="sunlit meadow",
        extra_prompt="see-through white dress, bare skin visible through fabric",
    )
    assert "sunlit meadow" in clip_l
    assert "naked with see through dress" in clip_l
    assert "see-through white dress" in clip_l
    assert "natural pores" not in clip_l.lower()
    assert "tasteful erotic photography" not in clip_l
    assert "natural pores" in t5.lower() or "skin texture" in t5.lower()
    assert "sunlit meadow" in t5


def test_clothed_outfit_drops_nude_character_style():
    contract = build_prompt_contract(
        appearance=AppearanceProfile(
            style_keywords=["tasteful full nude", "raw photo"],
            freeform_notes="candid nude, natural expression",
        ),
        boundaries=BoundariesProfile(),
        trigger_word="sks_aria_v1",
    )
    pos, _ = render_flux_prompts(contract, theme="outdoor_day", outfit_hint="denim jacket")
    assert "nude" not in pos
    assert "wearing denim jacket" in pos
    assert "raw photo" in pos
    assert "natural expression" in pos


def test_wardrobe_used_when_shot_has_no_outfit():
    contract = build_prompt_contract(
        appearance=AppearanceProfile(typical_wardrobe=["silk slip"]),
        boundaries=BoundariesProfile(),
        trigger_word="sks_aria_v1",
    )
    pos, _ = render_flux_prompts(contract, theme="portrait")
    assert "silk slip" in pos


def test_legacy_contract_wardrobe_style_token_is_dropped_for_outfit():
    contract = build_prompt_contract(
        appearance=AppearanceProfile(hair_color="blonde"),
        boundaries=BoundariesProfile(),
        trigger_word="sks_legacy_v1",
    )
    contract.style_tokens = ["wardrobe: silk slip, robe open", "raw photo"]
    pos, _ = render_flux_prompts(contract, theme="portrait", outfit_hint="denim jacket")
    assert "silk slip" not in pos
    assert "robe open" not in pos
    assert "wearing denim jacket" in pos
    assert "raw photo" in pos


def test_render_deduplicates_repeated_tokens():
    contract = build_prompt_contract(
        appearance=AppearanceProfile(
            hair_color="auburn",
            freeform_notes="auburn, real human skin texture, photorealistic photograph",
        ),
        boundaries=BoundariesProfile(),
        trigger_word="sks_aria_v1",
    )
    pos, _ = render_flux_prompts(contract, theme="portrait")
    tokens = [t.strip().lower() for t in pos.split(",")]
    assert len(tokens) == len(set(tokens))


def test_product_prompt_fragment_defaults():
    assert product_prompt_fragment(name=None) is None
    frag = product_prompt_fragment(name="Vial X", placement="featured")
    assert frag is not None
    assert "Vial X" in frag
    assert "advertisement" in frag.lower() or "hero" in frag.lower()
