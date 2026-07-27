"""Build PromptContract from structured character profiles."""

from __future__ import annotations

from instantimpact_common.enums import Pipeline
from instantimpact_common.safety_lists import ADULT_APPEARANCE_TOKENS, GLOBAL_NEGATIVE_FRAGMENTS
from instantimpact_common.schemas import (
    AppearanceProfile,
    BoundariesProfile,
    PromptContract,
)


def build_prompt_contract(
    *,
    appearance: AppearanceProfile | dict,
    boundaries: BoundariesProfile | dict,
    trigger_word: str | None,
    pipeline: Pipeline = Pipeline.FLUX,
) -> PromptContract:
    if isinstance(appearance, dict):
        appearance = AppearanceProfile.model_validate(appearance)
    if isinstance(boundaries, dict):
        boundaries = BoundariesProfile.model_validate(boundaries)

    appearance_tokens: list[str] = []
    for field in (
        appearance.skin_tone,
        appearance.face_shape,
        appearance.eye_color,
        appearance.eye_shape,
        appearance.hair_color,
        appearance.hair_length,
        appearance.hair_style,
        appearance.body_type,
        appearance.height_hint,
        appearance.makeup_style,
        appearance.ethnicity_hint,
    ):
        if field:
            appearance_tokens.append(str(field).strip())

    appearance_tokens.extend(f.strip() for f in appearance.distinguishing_features if f.strip())
    style_tokens = [s.strip() for s in appearance.style_keywords if s.strip()]
    if appearance.typical_wardrobe:
        style_tokens.append("wardrobe: " + ", ".join(appearance.typical_wardrobe))

    subject_tokens = list(ADULT_APPEARANCE_TOKENS)
    if trigger_word:
        subject_tokens.insert(0, trigger_word)

    quality_tokens = [
        "photorealistic",
        "high detail skin",
        "natural pores",
        "consistent facial identity",
        "professional photography",
    ]

    negative = list(GLOBAL_NEGATIVE_FRAGMENTS)
    for ban in boundaries.hard_bans:
        if ban and ban.strip():
            negative.append(ban.strip())

    return PromptContract(
        subject_tokens=subject_tokens,
        appearance_tokens=appearance_tokens,
        style_tokens=style_tokens,
        quality_tokens=quality_tokens,
        negative_tokens=negative,
        trigger_word=trigger_word,
        pipeline=pipeline,
        raw_notes=appearance.freeform_notes,
    )
