"""Flux-specific prompt rendering from PromptContract + scene hints."""

from __future__ import annotations

from instantimpact_common.schemas import PromptContract

from instantimpact_prompts.product import product_prompt_fragment
from instantimpact_prompts.themes import THEME_HINTS

# Character defaults that read as indoors and would fight an outdoor scene request.
_INDOOR_STYLE_MARKERS = ("studio", "window light", "indoor", "bedroom", "bathroom")

_OUTFIT_STATE_PREFIXES = ("nude", "naked", "topless", "wearing ")


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

    parts: list[str] = []
    # Lead with photo intent — Flux weights early tokens heavily
    parts.append("photorealistic photograph")
    parts.extend(contract.subject_tokens)
    parts.extend(contract.appearance_tokens)

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

    parts.extend(_filter_style_for_scene(style_tokens, scene))
    notes = _strip_wardrobe_hedges(contract.raw_notes, replaced=bool(outfit))
    if notes:
        parts.append(notes)
    parts.extend(contract.quality_tokens)

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


def _filter_style_for_scene(style_tokens: list[str], scene: str) -> list[str]:
    if "outdoor" not in scene.lower():
        return style_tokens
    return [s for s in style_tokens if not any(m in s.lower() for m in _INDOOR_STYLE_MARKERS)]


def _strip_wardrobe_hedges(notes: str | None, *, replaced: bool) -> str | None:
    """Drop clauses like "works nude as well as clothed" when a shot names an outfit."""
    if not notes or not replaced:
        return notes
    kept = [c.strip() for c in notes.split(",") if "clothed" not in c.lower()]
    return ", ".join(c for c in kept if c) or None


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
