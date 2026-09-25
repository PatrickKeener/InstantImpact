"""LoRA dataset captions: trigger + what varies. Identity stays on the trigger."""

from __future__ import annotations

from typing import Any

from instantimpact_prompts.themes import THEME_HINTS

# Shorter than generation hints so every caption stays variation-only.
_THEME_VARIATION: dict[str, str] = {
    "portrait": "head-and-shoulders portrait, looking at camera, soft window light",
    "casual_bedroom": "casual bedroom, relaxed pose, soft daylight",
    "lingerie_set": "lingerie editorial, directional studio light, confident pose",
    "outdoor_day": "outdoors in daylight, candid documentary framing",
    "gym": "gym, athletic pose, available light",
    "mirror_selfie": "mirror selfie, phone in hand, indoor ambient light",
    "cosplay": "costume, dramatic photographic lighting",
    "glamour": "editorial glamour, directional studio light",
}

_OUTFIT_STATE_PREFIXES = ("nude", "naked", "topless", "wearing ")


def training_caption(
    *,
    trigger: str,
    theme: str | None = None,
    outfit_hint: str | None = None,
    pose_hint: str | None = None,
    location_hint: str | None = None,
    extra_prompt: str | None = None,
    prompt_positive: str | None = None,
) -> str:
    """Describe pose, light, outfit, and crop. Do not restated hair/eyes/body."""
    parts: list[str] = [trigger.strip(), "adult woman"]
    theme_key = (theme or "").strip()
    if not theme_key and prompt_positive:
        theme_key = _theme_from_prompt(prompt_positive)
    if theme_key:
        parts.append(_THEME_VARIATION.get(theme_key, theme_key.replace("_", " ")))
    if location_hint and location_hint.strip():
        parts.append(location_hint.strip())
    if pose_hint and pose_hint.strip():
        parts.append(pose_hint.strip())
    outfit = (outfit_hint or "").strip()
    if outfit:
        if outfit.lower().startswith(_OUTFIT_STATE_PREFIXES):
            parts.append(outfit)
        else:
            parts.append(f"wearing {outfit}")
    extra = (extra_prompt or "").strip()
    if extra:
        parts.append(extra[:160])
    return ", ".join(_dedupe(parts))


def caption_from_asset(*, trigger: str, asset: Any) -> str:
    """Build a caption from an Asset row (meta first, then the stored prompt)."""
    meta = getattr(asset, "meta_json", None) or {}
    if not isinstance(meta, dict):
        meta = {}
    return training_caption(
        trigger=trigger,
        theme=meta.get("theme"),
        outfit_hint=meta.get("outfit_hint"),
        pose_hint=meta.get("pose_hint"),
        location_hint=meta.get("location_hint"),
        extra_prompt=meta.get("extra_prompt"),
        prompt_positive=getattr(asset, "prompt_positive", None),
    )


def _theme_from_prompt(prompt: str) -> str | None:
    low = prompt.lower()
    for key in _THEME_VARIATION:
        token = key.replace("_", " ")
        hint = THEME_HINTS.get(key, "").split(",")[0].lower()
        if key in low or token in low or (hint and hint in low):
            return key
    return None


def _dedupe(parts: list[str]) -> list[str]:
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
