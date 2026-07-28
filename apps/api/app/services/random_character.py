"""Curated random adult synthetic persona builder (no LLM required)."""

from __future__ import annotations

import random
from typing import Any

from app.schemas.characters import CharacterCreate
from instantimpact_common.enums import AgeAppearanceBand
from instantimpact_common.schemas import (
    AppearanceProfile,
    BoundariesProfile,
    PersonalityProfile,
    SpeakingStyle,
)

# First names only — generic, not celebrity-targeted
_FIRST_NAMES = [
    "Ava", "Mia", "Nora", "Elena", "Sofia", "Isla", "Luna", "Chloe", "Zoe", "Maya",
    "Aria", "Layla", "Camila", "Riley", "Harper", "Nova", "Ivy", "Ruby", "Sienna", "Freya",
    "Amara", "Keira", "Tessa", "Nina", "Vera", "Iris", "Lydia", "Sloane", "Quinn", "Eden",
    "Jasmine", "Priya", "Aisha", "Mei", "Hana", "Yara", "Ines", "Clara", "Dahlia", "Wren",
]

_AGE_BANDS = [
    (AgeAppearanceBand.MID_20S, 24, 27),
    (AgeAppearanceBand.LATE_20S, 27, 29),
    (AgeAppearanceBand.THIRTIES, 30, 35),
]

_SKIN = [
    "fair porcelain skin",
    "light skin with warm undertone",
    "medium olive skin",
    "golden tan skin",
    "light brown skin",
    "deep brown skin",
    "rich dark skin",
]

_ETHNICITY_HINTS = [
    "Northern European features",
    "Mediterranean features",
    "East Asian features",
    "South Asian features",
    "Latina features",
    "Middle Eastern features",
    "West African features",
    "mixed heritage features",
    "Slavic features",
    "Southeast Asian features",
]

_HAIR_COLOR = [
    "platinum blonde", "honey blonde", "dirty blonde", "strawberry blonde",
    "light brown", "chestnut brown", "dark brown", "jet black",
    "auburn", "copper red", "soft black with highlights",
]

_HAIR_LENGTH = ["chin-length", "shoulder-length", "mid-back length", "long flowing"]
_HAIR_STYLE = [
    "loose waves", "straight sleek", "soft curls", "beach waves",
    "half-up style", "layered cut", "curtain bangs", "natural texture",
]

_EYE_COLOR = ["blue", "green", "hazel", "brown", "dark brown", "gray-blue", "amber"]
_EYE_SHAPE = ["almond-shaped eyes", "round eyes", "hooded eyes", "upturned eyes"]
_FACE = ["oval face", "heart-shaped face", "soft square face", "diamond face", "round face"]
_BODY = [
    "slim athletic build", "curvy hourglass figure", "petite frame",
    "tall lean build", "soft feminine figure", "fit toned physique",
]
_HEIGHT = ["petite ~5'2\"", "average ~5'5\"", "tall ~5'9\""]
_MAKEUP = [
    "natural no-makeup look", "soft glam makeup", "nude lips and defined eyes",
    "dewy skin minimal makeup", "classic red lip evening look",
]
_WARDROBE = [
    ["oversized knits", "denim", "sneakers"],
    ["silk blouses", "tailored trousers", "heels"],
    ["athleisure", "sports bras", "leggings"],
    ["sundresses", "sandals", "straw bags"],
    ["leather jackets", "black jeans", "boots"],
    ["lingerie and robes", "silk slips"],
    ["crop tops", "high-waist jeans", "gold jewelry"],
]
_STYLE = [
    ["soft natural light", "intimate portrait"],
    ["editorial fashion", "clean studio"],
    ["warm lifestyle", "candid feel"],
    ["glamour photography", "polished"],
    ["boudoir aesthetic", "moody shadows"],
]
_FEATURES = [
    "light freckles across nose", "beauty mark near lip", "dimples when smiling",
    "high cheekbones", "full lips", "defined jawline", "soft smile lines",
    "long lashes", "subtle gap between teeth",
]
_TRAITS = [
    "confident", "playful", "warm", "curious", "witty", "calm", "flirty",
    "ambitious", "creative", "grounded", "adventurous", "empathetic",
]
_TONES = ["warm", "playful", "direct", "soft-spoken", "confident"]
_ENERGY = ["laid-back", "high-energy", "balanced", "sultry calm"]
_HUMOR = ["dry wit", "playful teasing", "self-deprecating", "light banter"]
_INTERESTS = [
    "photography", "yoga", "travel", "cooking", "vinyl records", "hiking",
    "fashion design", "coffee culture", "contemporary art", "fitness",
]
_NICHES = [
    "lifestyle", "glamour", "fitness", "fashion", "boudoir", "casual", "editorial",
]
_FORMALITY = ["casual", "warm", "playful", "direct"]
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
    """Build a CharacterCreate payload with randomized adult-safe fields."""
    rng = random.Random(seed)

    first = _pick(rng, _FIRST_NAMES)
    # Disambiguate common names
    suffix = rng.randint(2, 99)
    display_name = first if rng.random() > 0.35 else f"{first} {suffix}"

    band, age_lo, age_hi = _pick(rng, _AGE_BANDS)
    age_min = rng.randint(max(21, age_lo), age_hi)

    hair_color = _pick(rng, _HAIR_COLOR)
    eye_color = _pick(rng, _EYE_COLOR)
    body = _pick(rng, _BODY)
    ethnicity = _pick(rng, _ETHNICITY_HINTS)
    skin = _pick(rng, _SKIN)

    features = _sample(rng, _FEATURES, k=rng.randint(1, 2))
    style_kw = _pick(rng, _STYLE)
    wardrobe = _pick(rng, _WARDROBE)
    traits = _sample(rng, _TRAITS, k=rng.randint(3, 5))
    interests = _sample(rng, _INTERESTS, k=rng.randint(2, 4))
    niches = _sample(rng, _NICHES, k=rng.randint(1, 3))

    tone = _pick(rng, _TONES)
    energy = _pick(rng, _ENERGY)
    humor = _pick(rng, _HUMOR)
    formality = _pick(rng, _FORMALITY)
    emoji = _pick(rng, _EMOJI)

    bio = (
        f"Synthetic adult persona. {tone.capitalize()} energy ({energy}), "
        f"into {', '.join(interests[:2])}. Photogenic {body.split()[0]} look."
    )

    examples = [
        f"hey — it's {first}. glad you're here.",
        f"slow morning energy today. coffee first, then chaos.",
        f"tell me what kind of shoot vibe you want next.",
    ]

    # Adult content allowed by default for this studio; user can tighten later
    content_allowed = _sample(
        rng,
        ["portrait", "lingerie", "boudoir", "implied nude", "casual lifestyle", "glamour"],
        k=rng.randint(2, 4),
    )
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
        f"clearly adult woman age {age_min}+, {ethnicity}, {skin}, "
        f"{hair_color} hair, {eye_color} eyes, {body}, consistent facial identity"
    )

    appearance = AppearanceProfile(
        ethnicity_hint=ethnicity,
        skin_tone=skin,
        face_shape=_pick(rng, _FACE),
        eye_color=eye_color,
        eye_shape=_pick(rng, _EYE_SHAPE),
        hair_color=hair_color,
        hair_style=_pick(rng, _HAIR_STYLE),
        hair_length=_pick(rng, _HAIR_LENGTH),
        body_type=body,
        height_hint=_pick(rng, _HEIGHT),
        distinguishing_features=features,
        style_keywords=list(style_kw),
        makeup_style=_pick(rng, _MAKEUP),
        typical_wardrobe=list(wardrobe),
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
        trigger_word=None,  # service derives sks_* trigger
    )
