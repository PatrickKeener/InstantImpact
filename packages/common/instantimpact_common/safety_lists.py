"""Deny-list categories and hard negative fragments.

Enforcement is lexical + schema + human gates — not visual age detection.
Lookalike prevention is policy/UX, not guaranteed detection.
"""

from __future__ import annotations

# Categories that always hard-fail enqueue / brief validation
DENY_CATEGORIES: dict[str, list[str]] = {
    "underage_language": [
        "child",
        "children",
        "kid",
        "kids",
        "minor",
        "underage",
        "teen",
        "teenager",
        "schoolgirl",
        "schoolboy",
        "loli",
        "shota",
        "young girl",
        "young boy",
        "barely legal",
        "18 year",
        "18yo",
        "19 year",
        "19yo",
        "high school",
        "middle school",
    ],
    "real_person_targeting": [
        # Soft signals only — real enforcement is attestation + no scrape tools
        "celebrity lookalike",
        "looks like celebrity",
        "exact replica of",
        "clone of real",
    ],
    "non_consensual": [
        "nonconsensual",
        "non-consensual",
        "deepfake of",
        "revenge porn",
    ],
}

# Always appended to negative prompts for Flux stills
GLOBAL_NEGATIVE_FRAGMENTS: list[str] = [
    "child",
    "children",
    "kid",
    "teen",
    "underage",
    "young child",
    "infant",
    "toddler",
    "loli",
    "shota",
    "watermark",
    "text overlay",
    "logo",
    "deformed hands",
    "extra fingers",
    "mutated",
    "low quality",
    "blurry face",
    # Anti-illustration / cartoon drift (common with Flux FP8)
    "cartoon",
    "anime",
    "manga",
    "comic",
    "illustration",
    "drawing",
    "painting",
    "digital art",
    "3d render",
    "cgi",
    "pixar",
    "disney",
    "stylized",
    "cel shaded",
    "airbrushed skin",
    "plastic skin",
    "doll-like",
    "uncanny",
    "overprocessed",
    "oversaturated",
    "fake skin",
    "deformed nipples",
    "misshapen nipples",
    "extra nipples",
    "third nipple",
    "misplaced nipples",
    "melted nipples",
    "huge areolas",
    "puffy cartoon nipples",
    "inverted nipples",
    "glowing nipples",
    "asymmetrical nipples extreme",
]

# Positive quality stack for photoreal stills
PHOTOREAL_QUALITY_TOKENS: list[str] = [
    "photorealistic photograph",
    "real human skin texture",
    "natural skin pores",
    "subtle skin imperfections",
    "natural lighting",
    "shot on 85mm lens",
    "shallow depth of field",
    "sharp eyes",
    "professional photography",
    "raw photo",
    "true-to-life colors",
]

# Nude anatomy guidance, kept out of the tail quality stack on purpose.
#
# Flux.1-dev's training set was NSFW-filtered, so its prior for bare chest
# anatomy is weak and it defaults to smoothing the area over. The negative
# prompt cannot correct this because Flux runs at CFG 1.0, where negative
# conditioning has no effect. That leaves prompt position as the only lever:
# these have to land early, next to the wardrobe clause, to do anything.
# A dedicated anatomy/realism LoRA is the actual fix (see FluxPipelineParams
# .detail_lora_name) because it restores the missing prior.
NUDE_ANATOMY_DETAIL = (
    "anatomically correct bare chest, clearly defined natural nipples, "
    "soft-edged areolas slightly darker than the surrounding skin, "
    "fine skin detail in sharp focus"
)
NUDE_ANATOMY_TAGS = "anatomically correct nipples and areolas, sharp skin detail"

# Age-positive tokens encouraged in subject line
ADULT_APPEARANCE_TOKENS: list[str] = [
    "clearly adult woman",
    "21+ appearance",
    "mature adult features",
]

SYNTHETIC_DISCLOSURE_DEFAULT = (
    "This media is fully synthetic AI-generated content. "
    "It does not depict a real person. Age appearance is 21+."
)
