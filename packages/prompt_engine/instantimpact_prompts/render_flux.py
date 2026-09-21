"""Flux-specific prompt rendering from PromptContract + scene hints."""

from __future__ import annotations

from instantimpact_common.schemas import PromptContract

from instantimpact_prompts.product import product_prompt_fragment
from instantimpact_prompts.themes import THEME_HINTS

# Character defaults that read as indoors and would fight an outdoor scene request.
_INDOOR_STYLE_MARKERS = ("studio", "window light", "indoor", "bedroom", "bathroom")
_OUTFIT_STATE_PREFIXES = ("nude", "naked", "topless", "wearing ")
_REVEALING_MARKERS = ("nude", "naked", "topless", "see-through", "see through", "sheer")
_ANATOMY_MARKERS = ("breast", "nipple", "areola")


def render_flux_prompts(
    contract: PromptContract | dict,
    *,
    theme: str = "portrait",
    outfit_hint: str | None = None,
    pose_hint: str | None = None,
    location_hint: str | None = None,
    extra_prompt: str | None = None,
    product_name: str | None = None,
    product_description: str | None = None,
    product_placement: str | None = None,
) -> tuple[str, str]:
    """Return (positive, negative) prompt strings for Flux.

    Per-shot intent (theme, outfit, pose, location) is emitted ahead of the
    character's default style/wardrobe so it survives both Flux's early-token
    bias and the 77-token CLIP-L window.
    """
    if isinstance(contract, dict):
        contract = PromptContract.model_validate(contract)

    style_tokens, wardrobe_tokens = _split_wardrobe(contract)
    scene = THEME_HINTS.get(theme, theme.replace("_", " "))
    outfit = (outfit_hint or "").strip()
    exposure = outfit or ", ".join(wardrobe_tokens)
    revealing = _contains_any(exposure, _REVEALING_MARKERS)

    parts: list[str] = []
    # Lead with photo intent — Flux weights early tokens heavily
    parts.append("photorealistic photograph")
    parts.extend(contract.subject_tokens)

    # Shot-specific instructions must precede detailed identity attributes so
    # both Flux text encoders receive the requested scene and wardrobe.
    parts.append(scene)
    if outfit:
        # Avoid "wearing nude" awkwardness; pass outfit as-is if it already describes state
        if outfit.lower().startswith(_OUTFIT_STATE_PREFIXES):
            parts.append(outfit)
        else:
            parts.append(f"wearing {outfit}")
    else:
        # Character wardrobe is only a fallback; an explicit outfit replaces it
        parts.extend(wardrobe_tokens)
    if pose_hint:
        parts.append(pose_hint)
    if location_hint:
        parts.append(f"location: {location_hint}")
    product_clause = product_prompt_fragment(
        name=product_name,
        description=product_description,
        placement=product_placement,
    )
    if product_clause:
        parts.append(product_clause)
    if extra_prompt:
        parts.append(extra_prompt)

    parts.extend(contract.appearance_tokens)
    parts.extend(_filter_style_for_shot(style_tokens, scene=scene, outfit=outfit))
    notes = _filter_notes_for_shot(contract.raw_notes, scene=scene, outfit=outfit)
    if notes:
        parts.append(notes)
    parts.extend(
        _filter_quality_for_shot(contract.quality_tokens, scene=scene, revealing=revealing)
    )

    positive = ", ".join(_dedupe_tokens(parts))
    negative = ", ".join(_dedupe_tokens(contract.negative_tokens))
    return positive, negative


def _split_wardrobe(contract: PromptContract) -> tuple[list[str], list[str]]:
    """Separate wardrobe from style tokens.

    Contracts written before wardrobe_tokens existed stored it as a single
    "wardrobe: a, b" style token, so unpack that shape too.
    """
    style: list[str] = []
    wardrobe: list[str] = [w.strip() for w in contract.wardrobe_tokens if w.strip()]
    for token in contract.style_tokens:
        if token.strip().lower().startswith("wardrobe:"):
            legacy = token.split(":", 1)[1]
            wardrobe.extend(w.strip() for w in legacy.split(",") if w.strip())
        elif token.strip():
            style.append(token.strip())
    return style, wardrobe


def _filter_style_for_shot(style_tokens: list[str], *, scene: str, outfit: str) -> list[str]:
    filtered = style_tokens
    if "outdoor" in scene.lower():
        filtered = [s for s in filtered if not _contains_any(s, _INDOOR_STYLE_MARKERS)]
    if outfit and not _contains_any(outfit, _REVEALING_MARKERS):
        filtered = [s for s in filtered if not _contains_any(s, _REVEALING_MARKERS)]
    return filtered


def _filter_notes_for_shot(notes: str | None, *, scene: str, outfit: str) -> str | None:
    """Remove profile-note clauses that contradict explicit shot direction."""
    if not notes:
        return notes
    kept = [c.strip() for c in notes.split(",")]
    if "outdoor" in scene.lower():
        kept = [c for c in kept if not _contains_any(c, _INDOOR_STYLE_MARKERS)]
    if outfit:
        if _contains_any(outfit, _REVEALING_MARKERS):
            kept = [c for c in kept if "clothed" not in c.lower()]
        else:
            kept = [c for c in kept if not _contains_any(c, _REVEALING_MARKERS)]
    return ", ".join(c for c in kept if c) or None


def _filter_quality_for_shot(
    quality_tokens: list[str], *, scene: str, revealing: bool
) -> list[str]:
    filtered = quality_tokens
    if not revealing:
        filtered = [q for q in filtered if not _contains_any(q, _ANATOMY_MARKERS)]
    if _contains_any(scene, ("mm lens", "smartphone camera")):
        filtered = [q for q in filtered if q.lower() != "shot on 85mm lens"]
    return filtered


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    value = text.lower()
    return any(marker in value for marker in markers)


def _dedupe_tokens(parts: list[str]) -> list[str]:
    """Flatten to comma-separated tokens and drop repeats, preserving first position."""
    seen: set[str] = set()
    unique: list[str] = []
    for part in parts:
        for token in part.split(","):
            token = token.strip()
            key = token.lower()
            if token and key not in seen:
                seen.add(key)
                unique.append(token)
    return unique
