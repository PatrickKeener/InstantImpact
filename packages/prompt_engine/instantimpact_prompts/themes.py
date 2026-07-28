"""Theme → prompt fragment map for content briefs."""

# Keep themes photography-first; avoid "stylized" / illustration language.
THEME_HINTS: dict[str, str] = {
    "portrait": (
        "intimate photographic portrait, soft natural window light, looking at camera, "
        "realistic skin, 85mm photo"
    ),
    "casual_bedroom": (
        "casual bedroom setting, soft daylight through window, relaxed natural pose, "
        "lifestyle photograph"
    ),
    "lingerie_set": (
        "tasteful lingerie, elegant soft studio photography lighting, confident pose, "
        "fashion catalog photo"
    ),
    "outdoor_day": (
        "outdoor daylight, natural environment, candid documentary photo feel, "
        "real ambient light"
    ),
    "gym": "athletic wear, gym environment, energetic pose, sports photography",
    "mirror_selfie": (
        "mirror selfie composition, phone in hand, bathroom or bedroom, "
        "smartphone photo realism"
    ),
    "cosplay": (
        "costume cosplay, dramatic photographic lighting, convention photo, "
        "real fabric texture (not illustration)"
    ),
    "glamour": (
        "glamour photography, soft glam studio lighting, polished magazine photo, "
        "realistic makeup and skin"
    ),
}
