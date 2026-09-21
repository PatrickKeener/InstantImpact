"""Build PromptContract from structured character profiles."""

from __future__ import annotations

from instantimpact_common.enums import Pipeline
from instantimpact_common.safety_lists import (
    ADULT_APPEARANCE_TOKENS,
    GLOBAL_NEGATIVE_FRAGMENTS,
    PHOTOREAL_QUALITY_TOKENS,
)
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
    wardrobe_tokens = [w.strip() for w in appearance.typical_wardrobe if w.strip()]

    subject_tokens = list(ADULT_APPEARANCE_TOKENS)
    if trigger_word:
        subject_tokens.insert(0, trigger_word)

    quality_tokens = list(PHOTOREAL_QUALITY_TOKENS)
    quality_tokens.append("consistent facial identity")

    # Drop style keywords that push illustration/cartoon unless user insisted via freeform
    style_tokens = [
        s
        for s in style_tokens
        if not any(
            bad in s.lower()
            for bad in (
                "cartoon",
                "anime",
                "illustration",
                "stylized",
                "comic",
                "pixar",
                "cgi",
                "3d render",
            )
        )
    ]

    negative = list(GLOBAL_NEGATIVE_FRAGMENTS)
    for ban in boundaries.hard_bans:
        if ban and ban.strip():
            negative.append(ban.strip())

    # Nudge freeform notes toward photo if empty of camera language
    notes = appearance.freeform_notes
    if notes and "photo" not in notes.lower() and "camera" not in notes.lower():
        notes = f"{notes}, photorealistic DSLR photo"
    elif not notes:
        notes = "photorealistic DSLR photo of a real adult woman"

    return PromptContract(
        subject_tokens=subject_tokens,
        appearance_tokens=appearance_tokens,
        style_tokens=style_tokens,
        wardrobe_tokens=wardrobe_tokens,
        quality_tokens=quality_tokens,
        negative_tokens=negative,
        trigger_word=trigger_word,
        pipeline=pipeline,
        raw_notes=notes,
    )
