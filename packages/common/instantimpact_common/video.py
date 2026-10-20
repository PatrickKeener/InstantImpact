"""Wan 2.2 I2V clip length and lookbook motion helpers."""

from __future__ import annotations

WAN_FPS_DEFAULT = 16
WAN_FRAMES_MIN = 17
WAN_FRAMES_MAX = 161
# 121 frames at 16 fps ≈ 7.6s — a step up from the original 5s (81-frame) clips.
WAN_FRAMES_DEFAULT = 121
WAN_STEPS_DEFAULT = 20

# Wan temporal VAE wants 4n+1 frames. These land on ~5s / ~8s / ~10s at 16 fps.
DURATION_PRESETS_SECONDS: dict[int, int] = {
    5: 81,
    8: 121,
    10: 161,
}

DEFAULT_VIDEO_MOTION = (
    "gentle breathing, slight natural head movement, slow smooth camera push-in"
)
_LEGACY_DEFAULT_MOTION = (
    "subtle natural movement, gentle breathing, slight head turn, "
    "slow camera push-in, preserve face and clothing"
)
LOOKBOOK_MOTION = (
    "she slowly turns to show the outfit from multiple angles, natural weight shift, "
    "gentle fabric movement showing fit and material, hands lightly smooth the garment, "
    "slow commercial camera orbit, preserve the exact face, hair, and clothing"
)
PRODUCT_PRESENT_MOTION = (
    "she naturally presents the product toward camera, subtle smile, "
    "slow commercial camera orbit"
)

_GENERIC_MOTIONS = {DEFAULT_VIDEO_MOTION, _LEGACY_DEFAULT_MOTION}


def snap_wan_frames(frames: int | None, *, default: int = WAN_FRAMES_DEFAULT) -> int:
    """Clamp to the Wan 4n+1 grid used by Wan22ImageToVideoLatent."""
    value = default if frames is None else int(frames)
    value = max(WAN_FRAMES_MIN, min(WAN_FRAMES_MAX, value))
    snapped = ((value - 1 + 2) // 4) * 4 + 1
    return max(WAN_FRAMES_MIN, min(WAN_FRAMES_MAX, snapped))


def duration_seconds(frames: int, fps: int = WAN_FPS_DEFAULT) -> float:
    return round(int(frames) / max(int(fps), 1), 2)


def motion_for_item(
    *,
    motion: str | None,
    product_kind: str | None = None,
    product_placement: str | None = None,
) -> str:
    """Keep a generic camera move unless a product needs a show-off prompt."""
    text = (motion or "").strip() or DEFAULT_VIDEO_MOTION
    kind = (product_kind or "").strip().lower()
    place = (product_placement or "").strip().lower()
    if kind == "garment" and place == "wearing" and text in _GENERIC_MOTIONS:
        return LOOKBOOK_MOTION
    if kind == "product" and place in {"holding", "featured", "using"} and text in _GENERIC_MOTIONS:
        return PRODUCT_PRESENT_MOTION
    return text
