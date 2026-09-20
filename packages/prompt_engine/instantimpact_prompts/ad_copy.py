"""Offline marketing ad-copy renderer from a locked character voice.

No LLM required — deterministic templates + character few-shots.
Ollama rewrite can wrap this later behind ENABLE_CAPTIONS.
"""

from __future__ import annotations

import random
import re
from typing import Any

from instantimpact_common.schemas import MarketingVoice, PersonalityProfile, SpeakingStyle

CTA_BY_STYLE: dict[str, list[str]] = {
    "soft": [
        "If it feels like you, it's waiting.",
        "Whenever you're ready — I'll be here.",
        "Curious? Take a closer look.",
    ],
    "direct": [
        "Grab yours now.",
        "Shop it today.",
        "Don't wait — get it while it's here.",
    ],
    "playful": [
        "You're going to love this one.",
        "Trust me on this.",
        "Go on — treat yourself.",
    ],
    "urgent": [
        "Limited drop — move fast.",
        "This won't sit around.",
        "Now or miss it.",
    ],
}

EMOJI_BY_USE: dict[str, list[str]] = {
    "none": [],
    "light": ["✨", "💫", "🤍"],
    "heavy": ["✨", "💖", "🔥", "😍", "🫶"],
}


def _clean_list(items: list[str] | None) -> list[str]:
    out: list[str] = []
    for raw in items or []:
        s = str(raw).strip()
        if s and s not in out:
            out.append(s)
    return out


def _pick(rng: random.Random, options: list[str], fallback: str = "") -> str:
    if not options:
        return fallback
    return rng.choice(options)


def _apply_avoid(text: str, avoid: list[str]) -> str:
    out = text
    for word in avoid:
        if not word.strip():
            continue
        out = re.sub(re.escape(word), "", out, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", out).strip(" ,.-")


def _hashtags(
    *,
    style: str | None,
    product_name: str | None,
    brand: str | None,
    character_name: str,
) -> str:
    mode = (style or "none").lower()
    if mode == "none":
        return ""
    tags: list[str] = []
    if mode in ("light", "branded"):
        if brand:
            tags.append("#" + re.sub(r"[^A-Za-z0-9]+", "", brand))
        if product_name:
            tags.append("#" + re.sub(r"[^A-Za-z0-9]+", "", product_name)[:24])
    if mode == "branded":
        tags.append("#" + re.sub(r"[^A-Za-z0-9]+", "", character_name)[:20])
        tags.append("#ad")
    tags = [t for t in tags if len(t) > 2]
    return (" " + " ".join(tags[:4])) if tags else ""


def render_ad_copy(
    *,
    character_name: str,
    personality: PersonalityProfile | dict[str, Any] | None = None,
    speaking_style: SpeakingStyle | dict[str, Any] | None = None,
    marketing_voice: MarketingVoice | dict[str, Any] | None = None,
    product_name: str | None = None,
    product_brand: str | None = None,
    product_description: str | None = None,
    product_placement: str | None = None,
    theme: str | None = None,
    count: int = 3,
    seed: int | None = None,
) -> dict[str, Any]:
    """Return primary caption + variants shaped by the character marketing voice."""
    if isinstance(personality, dict):
        personality = PersonalityProfile.model_validate(personality)
    if isinstance(speaking_style, dict):
        speaking_style = SpeakingStyle.model_validate(speaking_style)
    if isinstance(marketing_voice, dict):
        marketing_voice = MarketingVoice.model_validate(marketing_voice)
    personality = personality or PersonalityProfile()
    speaking_style = speaking_style or SpeakingStyle()
    voice = marketing_voice or MarketingVoice()

    rng = random.Random(seed if seed is not None else 0)
    tone = (personality.tone or speaking_style.formality or "warm").strip()
    traits = _clean_list(personality.traits)[:4]
    samples = _clean_list(voice.sample_ads) or _clean_list(speaking_style.example_lines)
    value_props = _clean_list(voice.value_props)
    words_use = _clean_list(voice.words_to_use)
    words_avoid = _clean_list(voice.words_to_avoid)
    cta_style = (voice.cta_style or "soft").lower()
    if cta_style not in CTA_BY_STYLE:
        cta_style = "soft"
    emoji_use = (speaking_style.emoji_use or "light").lower()
    emojis = EMOJI_BY_USE.get(emoji_use, EMOJI_BY_USE["light"])

    product_label = (product_name or "").strip()
    brand = (product_brand or "").strip()
    desc = (product_description or "").strip()
    placement = (product_placement or "featured").strip()
    theme_label = (theme or "lifestyle").replace("_", " ").strip()

    hook_pool: list[str] = []
    if voice.tagline:
        hook_pool.append(voice.tagline.strip())
    if samples:
        hook_pool.extend(samples[:5])
    if traits:
        hook_pool.append(f"{traits[0].capitalize()} energy only.")
    hook_pool.append(f"Hey — it's {character_name}.")

    product_pool: list[str] = []
    if product_label:
        product_pool.extend(
            [
                f"I've been reaching for {product_label} on repeat.",
                f"Meet {product_label}" + (f" by {brand}" if brand else "") + ".",
                f"This is {product_label} — the one that actually fits my {theme_label} vibe.",
            ]
        )
        if desc:
            product_pool.append(f"{product_label}: {desc}.")
        if placement == "holding":
            product_pool.append(f"Caught me holding {product_label} like it's my new favorite.")
        elif placement == "using":
            product_pool.append(f"Real talk: I've been using {product_label} daily.")
    else:
        product_pool.append(f"New {theme_label} set just dropped from my world.")

    benefit_pool: list[str] = list(value_props) if value_props else []
    if words_use:
        benefit_pool.append("It's " + ", ".join(words_use[:3]) + ".")
    if personality.bio_short:
        benefit_pool.append(personality.bio_short.strip())
    if not benefit_pool:
        benefit_pool.append(f"Made for a {tone} {theme_label} moment.")

    cta_pool = list(CTA_BY_STYLE[cta_style])
    if voice.sign_off:
        cta_pool.append(voice.sign_off.strip())

    audience = (voice.audience or "").strip()
    variants: list[dict[str, str]] = []
    n = max(1, min(int(count), 8))
    for i in range(n):
        hook = _pick(rng, hook_pool)
        mid = _pick(rng, product_pool)
        benefit = _pick(rng, benefit_pool)
        cta = _pick(rng, cta_pool)
        parts = [hook, mid]
        if audience and i % 2 == 0:
            parts.append(f"For {audience}.")
        parts.append(benefit)
        parts.append(cta)
        body = " ".join(p for p in parts if p)
        body = _apply_avoid(body, words_avoid)
        if emojis and emoji_use != "none":
            body = f"{body} {_pick(rng, emojis)}"
        tags = _hashtags(
            style=voice.hashtag_style,
            product_name=product_label or None,
            brand=brand or None,
            character_name=character_name,
        )
        caption = (body + tags).strip()
        short = _apply_avoid(f"{hook} {cta}", words_avoid)
        if emojis and emoji_use == "light":
            short = f"{short} {_pick(rng, emojis)}".strip()
        variants.append(
            {
                "caption": caption,
                "short": short,
                "cta": cta,
                "hook": hook,
            }
        )

    primary = variants[0]
    return {
        "engine": "template_v1",
        "character_name": character_name,
        "tone": tone,
        "cta_style": cta_style,
        "product_name": product_label or None,
        "primary": primary["caption"],
        "short": primary["short"],
        "cta": primary["cta"],
        "variants": variants,
        "voice": voice.model_dump(),
    }
