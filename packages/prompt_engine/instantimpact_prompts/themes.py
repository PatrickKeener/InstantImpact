"""Theme → prompt fragment map for content briefs."""

# Keep themes photography-first; avoid "stylized" / illustration language.
THEME_HINTS: dict[str, str] = {
    "portrait": (
        "intimate head-and-shoulders portrait, soft natural window light, looking at camera, "
        "shot on an 85mm lens at f/2.8, realistic unretouched skin"
    ),
    "casual_bedroom": (
        "casual bedroom setting, soft daylight through window, relaxed natural pose, "
        "candid lifestyle photograph shot on a 50mm lens at f/2.8"
    ),
    "lingerie_set": (
        "tasteful lingerie editorial, soft directional studio lighting, confident pose, "
        "shot on an 85mm lens at f/2.8, true-to-life skin"
    ),
    "outdoor_day": (
        "clearly outdoors in daylight, natural environment visible behind the subject, "
        "candid documentary photograph shot on a 50mm lens at f/2.8, real ambient light"
    ),
    "gym": (
        "athletic wear in a real gym, energetic natural pose, available light sports "
        "photograph shot on a 35mm lens at f/2.8"
    ),
    "mirror_selfie": (
        "mirror selfie composition, phone in hand, bathroom or bedroom, "
        "authentic smartphone camera photograph, realistic reflections"
    ),
    "cosplay": (
        "costume cosplay, dramatic photographic lighting, convention photo, "
        "real fabric texture (not illustration)"
    ),
    "glamour": (
        "editorial glamour photograph, soft directional studio lighting, restrained retouching, "
        "shot on an 85mm lens at f/2.8, realistic makeup and true-to-life skin"
    ),
}
