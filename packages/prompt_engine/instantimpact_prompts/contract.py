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


# Older profiles stored weak "X features" hints. Flux treats those as optional
# and resamples race per seed. Expand them into an explicit woman + structure.
_ETHNICITY_LOCK = {
    "northern european features": "white Northern European woman, Northern European facial structure",
    "slavic features": "white Slavic woman, Slavic facial structure",
    "mediterranean features": "white Mediterranean woman, Mediterranean facial structure",
    "east asian features": "East Asian woman, East Asian facial structure",
    "south asian features": "South Asian woman, South Asian facial structure",
    "latina features": "Latina woman, Latin American facial structure",
    "middle eastern features": "Middle Eastern woman, Middle Eastern facial structure",
    "west african features": "Black woman, West African facial structure",
    "southeast asian features": "Southeast Asian woman, Southeast Asian facial structure",
    "mixed heritage features": "mixed-race woman, one consistent mixed facial structure",
}


def _lock_ethnicity(hint: str) -> str:
    key = hint.strip().lower()
    return _ETHNICITY_LOCK.get(key, hint.strip())


def _identity_lock_tokens(appearance: AppearanceProfile) -> list[str]:
    """Short race/face lock. Must stay at the front of both encoders."""
    tokens: list[str] = []
    if appearance.ethnicity_hint:
        tokens.append(_lock_ethnicity(str(appearance.ethnicity_hint)))
    if appearance.skin_tone:
        tokens.append(str(appearance.skin_tone).strip())
    hair_parts = [
        str(value).strip()
        for value in (appearance.hair_length, appearance.hair_color)
        if value
    ]
    if hair_parts:
        hair = " ".join(hair_parts)
        tokens.append(hair if "hair" in hair.lower() else f"{hair} hair")
    elif appearance.hair_color:
        color = str(appearance.hair_color).strip()
        tokens.append(color if "hair" in color.lower() else f"{color} hair")
    if appearance.eye_color:
        color = str(appearance.eye_color).strip()
        tokens.append(color if "eye" in color.lower() else f"{color} eyes")
    return tokens


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

    identity_lock = _identity_lock_tokens(appearance)

    appearance_tokens: list[str] = []
    appearance_tokens.extend(identity_lock)
    for field in (
        appearance.face_shape,
        appearance.body_type,
        appearance.height_hint,
        appearance.makeup_style,
    ):
        if field:
            appearance_tokens.append(str(field).strip())
    if appearance.eye_shape:
        shape = str(appearance.eye_shape).strip()
        appearance_tokens.append(shape if "eye" in shape.lower() else f"{shape} eyes")
    if appearance.hair_style:
        appearance_tokens.append(f"hair styled in {str(appearance.hair_style).strip()}")
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
        identity_lock_tokens=identity_lock,
        appearance_tokens=appearance_tokens,
        style_tokens=style_tokens,
        wardrobe_tokens=wardrobe_tokens,
        quality_tokens=quality_tokens,
        negative_tokens=negative,
        trigger_word=trigger_word,
        pipeline=pipeline,
        raw_notes=notes,
    )
