"""Product placement → prompt fragments for ad-style stills."""

from __future__ import annotations

PRODUCT_PLACEMENTS: dict[str, str] = {
    "holding": "holding and clearly displaying the product toward camera",
    "beside": "standing next to the product with the product clearly visible in frame",
    "using": "actively using the product in a natural lifestyle moment",
    "featured": (
        "product advertisement composition, hero product prominently featured "
        "with the person, packaging and label readable"
    ),
    "wearing": "wearing or accessorized with the product, brand mark clearly visible",
}

DEFAULT_PLACEMENT = "holding"


def normalize_placement(placement: str | None) -> str:
    key = (placement or DEFAULT_PLACEMENT).strip().lower().replace(" ", "_")
    return key if key in PRODUCT_PLACEMENTS else DEFAULT_PLACEMENT


def product_prompt_fragment(
    *,
    name: str | None,
    description: str | None = None,
    placement: str | None = None,
) -> str | None:
    """Build a prompt clause that asks Flux to include a named product."""
    label = (name or "").strip()
    if not label:
        return None
    place = normalize_placement(placement)
    action = PRODUCT_PLACEMENTS[place]
    parts = [f"commercial product placement: {action}", f"product is {label}"]
    desc = (description or "").strip()
    if desc:
        parts.append(f"product details: {desc}")
    parts.append("keep product shape, colors, and packaging accurate")
    return ", ".join(parts)
