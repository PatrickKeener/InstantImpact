"""Curated random adult synthetic persona builder (no LLM required).

Traits are sampled from coherent palettes so hair, eyes, skin, and ancestry
agree, and body/height/bust do not contradict. Independent rolls produced
impossible combinations that Flux cannot hold across a seed gallery.
"""

from __future__ import annotations

import random
from typing import Any, TypedDict

from app.schemas.characters import CharacterCreate
from instantimpact_common.enums import AgeAppearanceBand
from instantimpact_common.schemas import (
    AppearanceProfile,
    BoundariesProfile,
    PersonalityProfile,
    SpeakingStyle,
)

# First + surname only — generic, not celebrity-targeted.
_FIRST_NAMES = [
    "Ava", "Mia", "Nora", "Elena", "Sofia", "Isla", "Luna", "Chloe", "Zoe", "Maya",
    "Aria", "Layla", "Camila", "Riley", "Harper", "Nova", "Ivy", "Ruby", "Sienna", "Freya",
    "Amara", "Keira", "Tessa", "Nina", "Vera", "Iris", "Lydia", "Sloane", "Quinn", "Eden",
    "Jasmine", "Priya", "Aisha", "Mei", "Hana", "Yara", "Ines", "Clara", "Dahlia", "Wren",
    "Leila", "Noor", "Sable", "Marlowe", "Indira", "Kira",
]



class AncestryPalette(TypedDict):
    ethnicity: str
    skin: list[str]
    hair: list[str]
    eyes: list[str]
    surnames: list[str]


# One ancestry per character. Vague "features" / "mixed heritage" lets Flux
# pick a different race on every seed. Name the woman, the structure, and a
# tight skin/hair/eye set.
_PALETTES: list[AncestryPalette] = [
    {
        "ethnicity": "white Northern European woman, Northern European facial structure",
        "skin": ["fair porcelain skin", "light skin with cool undertone", "light skin with warm undertone"],
        "hair": ["platinum blonde", "honey blonde", "dirty blonde", "light brown", "chestnut brown", "auburn"],
        "eyes": ["blue", "green", "gray-blue", "hazel"],
        "surnames": ["Vale", "Hart", "Keene", "Ivers", "Berg", "Shaw", "Reed", "Hale"],
    },
    {
        "ethnicity": "white Slavic woman, Slavic facial structure",
        "skin": ["fair porcelain skin", "light skin with cool undertone"],
        "hair": ["platinum blonde", "dirty blonde", "light brown", "dark brown"],
        "eyes": ["blue", "gray-blue", "green"],
        "surnames": ["Voss", "Maren", "Volkov", "Hale", "Keene"],
    },
    {
        "ethnicity": "white Mediterranean woman, Mediterranean facial structure",
        "skin": ["olive skin", "medium olive skin", "golden tan skin"],
        "hair": ["dark brown", "chestnut brown", "jet black"],
        "eyes": ["brown", "hazel", "dark brown", "green"],
        "surnames": ["Costa", "Romano", "Vale", "Cole"],
    },
    {
        "ethnicity": "East Asian woman, East Asian facial structure",
        "skin": ["light East Asian skin", "light skin with warm undertone", "light medium East Asian skin"],
        "hair": ["jet black", "dark brown"],
        "eyes": ["dark brown", "brown"],
        "surnames": ["Sato", "Nguyen", "Chen", "Park", "Hayashi"],
    },
    {
        "ethnicity": "South Asian woman, South Asian facial structure",
        "skin": ["light brown South Asian skin", "medium brown South Asian skin", "warm brown skin"],
        "hair": ["jet black", "dark brown"],
        "eyes": ["dark brown", "brown"],
        "surnames": ["Kaur", "Rahman", "Sharma", "Nair"],
    },
    {
        "ethnicity": "Latina woman, Latin American facial structure",
        "skin": ["golden tan skin", "medium olive skin", "light brown skin"],
        "hair": ["dark brown", "jet black", "chestnut brown"],
        "eyes": ["brown", "dark brown", "hazel"],
        "surnames": ["Diaz", "Solis", "Alvarez", "Rios", "Costa"],
    },
    {
        "ethnicity": "Middle Eastern woman, Middle Eastern facial structure",
        "skin": ["olive skin", "golden tan skin", "light brown olive skin"],
        "hair": ["jet black", "dark brown"],
        "eyes": ["dark brown", "brown", "hazel"],
        "surnames": ["Nadir", "Rahman", "Hassan", "Farah"],
    },
    {
        "ethnicity": "Black woman, West African facial structure",
        "skin": ["deep brown skin", "rich dark skin", "dark brown skin"],
        "hair": ["jet black", "dark brown"],
        "eyes": ["dark brown", "brown"],
        "surnames": ["Okoye", "Mensah", "Adeyemi", "Nwosu"],
    },
    {
        "ethnicity": "Southeast Asian woman, Southeast Asian facial structure",
        "skin": ["golden tan Southeast Asian skin", "light brown Southeast Asian skin", "medium brown skin"],
        "hair": ["jet black", "dark brown"],
        "eyes": ["dark brown", "brown"],
        "surnames": ["Nguyen", "Santos", "Rahman", "Sari"],
    },
]


class BodyPreset(TypedDict):
    body_type: str
    heights: list[str]
    breasts: list[str]


# Bust lives only in distinguishing_features so body_type does not fight it.
_BODIES: list[BodyPreset] = [
    {
        "body_type": "slim athletic adult figure, toned stomach",
        "heights": ["average ~5'5\"", "tall ~5'8\"", "tall ~5'9\""],
        "breasts": [
            "small natural breasts, soft realistic shape",
            "medium perky breasts, natural proportions",
        ],
    },
    {
        "body_type": "petite adult frame, narrow waist",
        "heights": ["petite ~5'2\"", "petite ~5'3\""],
        "breasts": [
            "small natural breasts, soft realistic shape",
            "medium perky breasts, natural proportions",
        ],
    },
    {
        "body_type": "soft hourglass adult figure, thick hips and thighs",
        "heights": ["average ~5'4\"", "average ~5'5\"", "average ~5'6\""],
        "breasts": [
            "medium full breasts, natural proportions",
            "full teardrop breasts with natural hang",
            "large round breasts, realistic weight and hang",
        ],
    },
    {
        "body_type": "curvy thick adult figure, soft belly, wide hips",
        "heights": ["average ~5'4\"", "average ~5'5\"", "average ~5'6\""],
        "breasts": [
            "full teardrop breasts with natural hang",
            "large round breasts, realistic weight and hang",
            "thick full breasts, soft natural shape",
        ],
    },
    {
        "body_type": "tall lean adult build, long legs",
        "heights": ["tall ~5'8\"", "tall ~5'9\"", "tall ~5'10\""],
        "breasts": [
            "small natural breasts, soft realistic shape",
            "medium perky breasts, natural proportions",
            "medium full breasts, natural proportions",
        ],
    },
    {
        "body_type": "fit toned adult physique, defined waist",
        "heights": ["average ~5'5\"", "average ~5'6\"", "tall ~5'8\""],
        "breasts": [
            "medium perky breasts, natural proportions",
            "athletic chest, medium natural breasts",
        ],
    },
    {
        "body_type": "voluptuous adult figure, thick thighs, soft curves",
        "heights": ["average ~5'4\"", "average ~5'5\"", "average ~5'6\""],
        "breasts": [
            "large round breasts, realistic weight and hang",
            "heavy natural breasts, realistic weight and hang",
        ],
    },
    {
        "body_type": "soft feminine adult figure, rounded hips",
        "heights": ["petite ~5'3\"", "average ~5'5\"", "average ~5'6\""],
        "breasts": [
            "medium full breasts, natural hang",
            "full teardrop breasts with natural hang",
        ],
    },
]

_HAIR_BY_LENGTH: dict[str, list[str]] = {
    "chin-length": ["sleek bob", "textured bob", "curtain bangs"],
    "shoulder-length": ["loose waves", "straight sleek", "layered cut", "curtain bangs"],
    "mid-back length": ["loose waves", "soft curls", "beach waves", "natural texture"],
    "long": ["loose waves", "soft curls", "beach waves", "straight sleek", "natural texture"],
}

_EYE_SHAPE = ["almond-shaped eyes", "round eyes", "hooded eyes", "upturned eyes"]
_FACE = ["oval face", "heart-shaped face", "soft square face", "diamond face", "round face"]
_MAKEUP = [
    "natural no-makeup look",
    "soft glam makeup",
    "nude lips and defined eyes",
    "dewy skin, minimal makeup",
    "classic red lip, otherwise natural",
]
# Default clothes only. Themes supply the shot outfit. Forced nude here
# leaks into every gym/outdoor still and bakes one wardrobe into the LoRA.
_WARDROBE = [
    ["casual loungewear", "oversized tee"],
    ["silk slip", "soft robe"],
    ["lingerie", "sheer robe"],
    ["fitted tank", "jeans"],
    ["knit sweater", "simple trousers"],
    ["athletic wear", "sports bra"],
    ["simple bikini"],
    ["little black dress"],
    ["nude", "bare skin"],
    ["topless", "waist-up bare"],
]
_STYLE = [
    ["lifestyle photograph", "available light"],
    ["editorial portrait", "shallow depth of field"],
    ["candid documentary framing"],
    ["glamour photography", "soft directional light"],
]
_FEATURES = [
    "light freckles across the nose",
    "beauty mark near the lip",
    "dimples when smiling",
    "high cheekbones",
    "full lips",
    "defined jawline",
    "soft smile lines",
    "long lashes",
    "subtle collarbones",
    "a small scar through the left eyebrow",
    "a faint gap between the front teeth",
]

_AGE_BANDS = [
    (AgeAppearanceBand.MID_20S, 24, 27),
    (AgeAppearanceBand.LATE_20S, 27, 29),
    (AgeAppearanceBand.THIRTIES, 30, 35),
]


class PersonaCluster(TypedDict):
    tone: str
    energy: str
    humor: str
    formality: str
    traits: list[str]


_CLUSTERS: list[PersonaCluster] = [
    {
        "tone": "warm",
        "energy": "laid-back",
        "humor": "playful teasing",
        "formality": "warm",
        "traits": ["warm", "playful", "curious", "empathetic", "grounded"],
    },
    {
        "tone": "playful",
        "energy": "high-energy",
        "humor": "light banter",
        "formality": "playful",
        "traits": ["playful", "witty", "adventurous", "confident", "creative"],
    },
    {
        "tone": "direct",
        "energy": "balanced",
        "humor": "dry wit",
        "formality": "direct",
        "traits": ["confident", "ambitious", "grounded", "witty", "calm"],
    },
    {
        "tone": "soft-spoken",
        "energy": "laid-back",
        "humor": "self-deprecating",
        "formality": "casual",
        "traits": ["calm", "empathetic", "curious", "creative", "warm"],
    },
    {
        "tone": "confident",
        "energy": "sultry calm",
        "humor": "dry wit",
        "formality": "warm",
        "traits": ["confident", "calm", "flirty", "grounded", "witty"],
    },
]

_INTERESTS = [
    "photography", "yoga", "travel", "cooking", "vinyl records", "hiking",
    "fashion design", "coffee culture", "contemporary art", "fitness",
    "film photography", "strength training", "ceramics",
]
_NICHES = [
    "lifestyle", "glamour", "fashion", "boudoir", "casual", "editorial", "fitness",
]
_EMOJI = ["none", "light", "heavy"]

_ATTESTATION = (
    "I confirm this is a fully synthetic AI-generated adult persona (21+ appearance), "
    "not based on a real identifiable person, created for local private content production."
)


def _pick(rng: random.Random, items: list[Any]) -> Any:
    return items[rng.randrange(len(items))]


def _sample(rng: random.Random, items: list[Any], k: int) -> list[Any]:
    k = min(k, len(items))
    return rng.sample(list(items), k)


def build_random_character_create(
    *,
    seed: int | None = None,
    auto_attest: bool = True,
) -> CharacterCreate:
    """Build a CharacterCreate payload with a coherent adult appearance."""
    rng = random.Random(seed)

    first = _pick(rng, _FIRST_NAMES)
    palette = _pick(rng, _PALETTES)
    last = _pick(rng, palette["surnames"])
    display_name = f"{first} {last}"

    band, age_lo, age_hi = _pick(rng, _AGE_BANDS)
    age_min = rng.randint(max(21, age_lo), age_hi)

    body = _pick(rng, _BODIES)
    hair_length = _pick(rng, list(_HAIR_BY_LENGTH))
    hair_style = _pick(rng, _HAIR_BY_LENGTH[hair_length])
    cluster = _pick(rng, _CLUSTERS)

    hair_color = _pick(rng, palette["hair"])
    eye_color = _pick(rng, palette["eyes"])
    skin = _pick(rng, palette["skin"])
    ethnicity = palette["ethnicity"]
    breasts = _pick(rng, body["breasts"])
    height = _pick(rng, body["heights"])

    features = _sample(rng, _FEATURES, k=rng.randint(1, 2))
    features = list(dict.fromkeys([*features, breasts]))
    style_kw = list(_pick(rng, _STYLE))
    clothed, bare = _WARDROBE[:-2], _WARDROBE[-2:]
    wardrobe = list(_pick(rng, bare if rng.random() < 0.25 else clothed))

    traits = _sample(rng, cluster["traits"], k=rng.randint(3, 5))
    interests = _sample(rng, _INTERESTS, k=rng.randint(2, 4))
    niches = _sample(rng, _NICHES, k=rng.randint(1, 3))
    emoji = _pick(rng, _EMOJI)

    tone = cluster["tone"]
    energy = cluster["energy"]
    humor = cluster["humor"]
    formality = cluster["formality"]

    bio = (
        f"Synthetic adult persona. {tone.capitalize()}, {energy}, "
        f"into {', '.join(interests[:2])}."
    )
    examples = [
        f"hey — it's {first.lower()}. glad you're here.",
        "slow morning. coffee first.",
        "tell me what kind of shoot vibe you want next.",
    ]

    content_allowed = [
        "nude",
        "naked",
        "topless",
        "lingerie",
        "boudoir",
        "portrait",
        "glamour",
        "casual lifestyle",
    ]
    hard_bans = [
        "underage",
        "teen",
        "real person likeness",
        "celebrity lookalike",
        "non-consensual",
    ]
    soft_limits = _sample(
        rng,
        ["extreme violence", "gore", "heavy drugs", "political content"],
        k=rng.randint(1, 2),
    )

    freeform = (
        f"clearly adult woman age {age_min}+, authentic photorealistic candid photograph, "
        "unretouched real skin texture, subtle natural imperfections, "
        "consistent facial identity"
    )

    appearance = AppearanceProfile(
        ethnicity_hint=ethnicity,
        skin_tone=skin,
        face_shape=_pick(rng, _FACE),
        eye_color=eye_color,
        eye_shape=_pick(rng, _EYE_SHAPE),
        hair_color=hair_color,
        hair_style=hair_style,
        hair_length=hair_length,
        body_type=body["body_type"],
        height_hint=height,
        distinguishing_features=features,
        style_keywords=list(style_kw),
        makeup_style=_pick(rng, _MAKEUP),
        typical_wardrobe=wardrobe,
        freeform_notes=freeform,
    )

    personality = PersonalityProfile(
        traits=traits,
        tone=tone,
        energy=energy,
        humor=humor,
        interests=interests,
        catchphrases=[f"that's so {first.lower()}", "okay but hear me out"],
        bio_short=bio,
    )

    boundaries = BoundariesProfile(
        hard_bans=hard_bans,
        soft_limits=soft_limits,
        content_allowed=content_allowed,
        notes="Random-generated profile — review before production lock.",
    )

    speaking = SpeakingStyle(
        formality=formality,
        emoji_use=emoji,
        vocabulary="contemporary casual",
        example_lines=examples,
    )

    return CharacterCreate(
        display_name=display_name,
        age_appearance_min=age_min,
        age_appearance_band=band,
        synthetic_confirmed=auto_attest,
        not_real_person_attested=auto_attest,
        attestation_text=_ATTESTATION if auto_attest else None,
        niche_tags=niches,
        appearance=appearance,
        personality=personality,
        boundaries=boundaries,
        speaking_style=speaking,
        trigger_word=None,
    )
