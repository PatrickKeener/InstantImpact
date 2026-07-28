"""Flux-specific prompt rendering from PromptContract + scene hints."""

from __future__ import annotations

from instantimpact_common.schemas import PromptContract
from instantimpact_prompts.themes import THEME_HINTS


def render_flux_prompts(
    contract: PromptContract | dict,
    *,
    theme: str = "portrait",
    outfit_hint: str | None = None,
    pose_hint: str | None = None,
    location_hint: str | None = None,
    extra_prompt: str | None = None,
) -> tuple[str, str]:
    """Return (positive, negative) prompt strings for Flux."""
    if isinstance(contract, dict):
        contract = PromptContract.model_validate(contract)

    parts: list[str] = []
    # Lead with photo intent — Flux weights early tokens heavily
    parts.append("photorealistic photograph")
    parts.extend(contract.subject_tokens)
    parts.extend(contract.appearance_tokens)
    parts.extend(contract.style_tokens)

    scene = THEME_HINTS.get(theme, theme.replace("_", " "))
    parts.append(scene)
    if outfit_hint:
        # Avoid "wearing nude" awkwardness; pass outfit as-is if it already describes state
        oh = outfit_hint.strip()
        if oh.lower().startswith(("nude", "naked", "topless", "wearing ")):
            parts.append(oh)
        else:
            parts.append(f"wearing {oh}")
    if pose_hint:
        parts.append(pose_hint)
    if location_hint:
        parts.append(f"location: {location_hint}")
    if extra_prompt:
        parts.append(extra_prompt)
    if contract.raw_notes:
        parts.append(contract.raw_notes)
    parts.extend(contract.quality_tokens)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for p in parts:
        key = p.strip().lower()
        if p.strip() and key not in seen:
            seen.add(key)
            unique.append(p.strip())

    positive = ", ".join(unique)
    neg_seen: set[str] = set()
    negatives: list[str] = []
    for n in contract.negative_tokens:
        key = n.strip().lower()
        if n.strip() and key not in neg_seen:
            neg_seen.add(key)
            negatives.append(n.strip())
    negative = ", ".join(negatives)
    return positive, negative
