"""Safety validation gateway — called on every GPU enqueue path."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from instantimpact_common.safety_lists import DENY_CATEGORIES


@dataclass
class SafetyResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    matched_category: str | None = None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def scan_text(text: str) -> SafetyResult:
    if not text:
        return SafetyResult(ok=True)
    normalized = _normalize(text)
    for category, terms in DENY_CATEGORIES.items():
        for term in terms:
            if term in normalized:
                return SafetyResult(
                    ok=False,
                    reasons=[f"Blocked term '{term}' in category '{category}'"],
                    matched_category=category,
                )
    return SafetyResult(ok=True)


def validate_character_for_generation(
    *,
    synthetic_confirmed: bool,
    age_appearance_min: int,
    not_real_person_attested: bool,
    status: str,
    texts: list[str] | None = None,
) -> SafetyResult:
    reasons: list[str] = []
    if not synthetic_confirmed:
        reasons.append("synthetic_confirmed must be true before generation")
    if age_appearance_min < 21:
        reasons.append("age_appearance_min must be >= 21")
    if not not_real_person_attested:
        reasons.append("not_real_person_attested required")
    if status == "archived":
        reasons.append("archived characters cannot generate")
    if status == "draft":
        # seed_gallery allowed after safety flags; other jobs blocked at service layer
        pass

    for t in texts or []:
        scan = scan_text(t)
        if not scan.ok:
            reasons.extend(scan.reasons)

    return SafetyResult(ok=len(reasons) == 0, reasons=reasons)


def validate_for_enqueue(
    *,
    job_type: str,
    character_status: str,
    synthetic_confirmed: bool,
    age_appearance_min: int,
    not_real_person_attested: bool,
    texts: list[str] | None = None,
    video_enabled: bool = False,
) -> SafetyResult:
    base = validate_character_for_generation(
        synthetic_confirmed=synthetic_confirmed,
        age_appearance_min=age_appearance_min,
        not_real_person_attested=not_real_person_attested,
        status=character_status,
        texts=texts,
    )
    reasons = list(base.reasons)

    if job_type in ("still_batch", "seed_gallery", "validation_sheet", "ref_embed"):
        if character_status not in ("draft", "bootstrap", "training", "ready"):
            reasons.append(f"status '{character_status}' cannot run {job_type}")
        if job_type == "still_batch" and character_status == "draft":
            reasons.append("still_batch requires bootstrap or ready (complete seed/refs first)")
        if job_type == "seed_gallery" and character_status not in ("draft", "bootstrap", "ready"):
            if character_status == "training":
                reasons.append("seed_gallery blocked while first-time training is running")

    if job_type == "lora_train" and character_status not in ("bootstrap", "ready"):
        reasons.append("lora_train requires bootstrap (first train) or ready (retrain)")

    if job_type.startswith("video") and not video_enabled:
        reasons.append("video generation is not enabled in MVP")

    # Scan brief/theme text
    for t in texts or []:
        scan = scan_text(t)
        if not scan.ok:
            reasons.extend(scan.reasons)

    # de-dupe
    uniq: list[str] = []
    for r in reasons:
        if r not in uniq:
            uniq.append(r)
    return SafetyResult(ok=len(uniq) == 0, reasons=uniq)
