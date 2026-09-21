from __future__ import annotations

import re
from datetime import datetime, timezone

from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Asset, Character, CharacterVersion
from app.schemas.characters import CharacterCreate, CharacterUpdate, LockCharacterRequest
from app.services.storage import get_layout
from instantimpact_common.enums import CharacterStatus, VersionStatus
from instantimpact_common.schemas import PipelineParams
from instantimpact_prompts.contract import build_prompt_contract
from instantimpact_prompts.render_flux import render_flux_prompts


class CharacterServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _unique_slug_base(name: str) -> str:
    base = slugify(name) or "character"
    return base[:100]


async def _ensure_unique_slug(db: AsyncSession, base: str, exclude_id: str | None = None) -> str:
    slug = base
    n = 2
    while True:
        q = await db.execute(select(Character).where(Character.slug == slug))
        existing = q.scalar_one_or_none()
        if existing is None or (exclude_id and existing.id == exclude_id):
            return slug
        slug = f"{base}-{n}"
        n += 1


def _default_trigger(display_name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", display_name.lower()).strip("_")
    return f"sks_{cleaned[:40]}_v1" if cleaned else "sks_persona_v1"


def version_to_dict(v: CharacterVersion) -> dict:
    return {
        "id": v.id,
        "character_id": v.character_id,
        "version_int": v.version_int,
        "status": v.status,
        "appearance": v.appearance_json or {},
        "personality": v.personality_json or {},
        "boundaries": v.boundaries_json or {},
        "speaking_style": v.speaking_style_json or {},
        "marketing_voice": v.marketing_voice_json or {},
        "niche_tags": v.niche_tags_json or [],
        "trigger_word": v.trigger_word,
        "lora_path": v.lora_path,
        "ref_pack_path": v.ref_pack_path,
        "prompt_contract": v.prompt_contract_json or {},
        "pipeline_params": v.pipeline_params_json or {},
        "locked_at": v.locked_at,
    }


def character_to_out(c: Character, version: CharacterVersion | None = None) -> dict:
    if version is None and c.versions:
        # Prefer locked, else highest version_int
        if c.locked_version_id:
            version = next((v for v in c.versions if v.id == c.locked_version_id), None)
        if version is None:
            version = max(c.versions, key=lambda x: x.version_int)
    return {
        "id": c.id,
        "slug": c.slug,
        "display_name": c.display_name,
        "status": c.status,
        "preferred_pipeline": c.preferred_pipeline,
        "age_appearance_min": c.age_appearance_min,
        "age_appearance_band": c.age_appearance_band,
        "synthetic_confirmed": c.synthetic_confirmed,
        "not_real_person_attested": c.not_real_person_attested,
        "attestation_text": c.attestation_text,
        "locked_version_id": c.locked_version_id,
        "retrain_version_id": c.retrain_version_id,
        "niche_tags": c.niche_tags_json or [],
        "created_at": c.created_at,
        "updated_at": c.updated_at,
        "current_version": version_to_dict(version) if version else None,
        "preview_thumb": None,
    }


async def list_characters(db: AsyncSession, include_archived: bool = False) -> list[dict]:
    q = select(Character).options(selectinload(Character.versions)).order_by(Character.updated_at.desc())
    if not include_archived:
        q = q.where(Character.status != CharacterStatus.ARCHIVED)
    rows = (await db.execute(q)).scalars().all()
    thumbs = await _preview_thumbs(db, [c.id for c in rows])
    out = []
    for c in rows:
        d = character_to_out(c)
        d["preview_thumb"] = thumbs.get(c.id)
        out.append(d)
    return out


async def _preview_thumbs(db: AsyncSession, character_ids: list[str]) -> dict[str, str]:
    if not character_ids:
        return {}
    q = (
        select(Asset)
        .where(Asset.character_id.in_(character_ids))
        .where(Asset.kind == "still")
        .where(Asset.decision == "approved")
        .order_by(Asset.created_at.desc())
    )
    thumbs: dict[str, str] = {}
    for a in (await db.execute(q)).scalars().all():
        if a.character_id in thumbs:
            continue
        thumbs[a.character_id] = a.thumb_path or a.path
    if len(thumbs) < len(character_ids):
        q2 = (
            select(Asset)
            .where(Asset.character_id.in_(character_ids))
            .where(Asset.kind == "still")
            .order_by(Asset.created_at.desc())
        )
        for a in (await db.execute(q2)).scalars().all():
            if a.character_id in thumbs:
                continue
            thumbs[a.character_id] = a.thumb_path or a.path
    return thumbs


async def get_character(db: AsyncSession, character_id: str) -> Character:
    q = await db.execute(
        select(Character)
        .options(selectinload(Character.versions))
        .where(Character.id == character_id)
    )
    c = q.scalar_one_or_none()
    if not c:
        raise CharacterServiceError("Character not found", 404)
    return c


async def character_to_out_with_thumb(db: AsyncSession, c: Character) -> dict:
    d = character_to_out(c)
    thumbs = await _preview_thumbs(db, [c.id])
    d["preview_thumb"] = thumbs.get(c.id)
    return d


async def create_random_character(
    db: AsyncSession,
    *,
    seed: int | None = None,
    auto_attest: bool = False,
    auto_bootstrap: bool = False,
) -> dict:
    """Create a fully filled random adult synthetic persona."""
    from app.services.random_character import build_random_character_create

    payload = build_random_character_create(seed=seed, auto_attest=auto_attest)
    character = await create_character(db, payload)
    if auto_bootstrap and character.get("synthetic_confirmed") and character.get(
        "not_real_person_attested"
    ):
        try:
            character = await mark_bootstrap(db, character["id"])
        except CharacterServiceError:
            # Leave as draft if bootstrap rules change
            pass
    return character


async def create_character(db: AsyncSession, payload: CharacterCreate) -> dict:
    base = payload.slug or _unique_slug_base(payload.display_name)
    slug = await _ensure_unique_slug(db, _unique_slug_base(base))
    trigger = payload.trigger_word or _default_trigger(payload.display_name)

    contract = build_prompt_contract(
        appearance=payload.appearance,
        boundaries=payload.boundaries,
        trigger_word=trigger,
    )
    params = PipelineParams().model_dump()

    character = Character(
        slug=slug,
        display_name=payload.display_name,
        status=CharacterStatus.DRAFT,
        preferred_pipeline=str(payload.preferred_pipeline),
        age_appearance_min=payload.age_appearance_min,
        age_appearance_band=str(payload.age_appearance_band),
        synthetic_confirmed=payload.synthetic_confirmed,
        not_real_person_attested=payload.not_real_person_attested,
        attestation_text=payload.attestation_text,
        niche_tags_json=payload.niche_tags,
    )
    db.add(character)
    await db.flush()

    version = CharacterVersion(
        character_id=character.id,
        version_int=1,
        status=VersionStatus.DRAFTING,
        appearance_json=payload.appearance.model_dump(),
        personality_json=payload.personality.model_dump(),
        boundaries_json=payload.boundaries.model_dump(),
        speaking_style_json=payload.speaking_style.model_dump(),
        marketing_voice_json=payload.marketing_voice.model_dump(),
        niche_tags_json=payload.niche_tags,
        trigger_word=trigger,
        pipeline_params_json=params,
        prompt_contract_json=contract.model_dump(),
        safety_profile_json={
            "age_appearance_min": payload.age_appearance_min,
            "age_appearance_band": str(payload.age_appearance_band),
            "synthetic_confirmed": payload.synthetic_confirmed,
        },
    )
    db.add(version)
    await db.flush()

    layout = get_layout()
    refs_dir = layout.refs_dir(character.id, 1)
    for sub in (refs_dir, layout.lora_dir(character.id, 1), layout.dataset_dir(character.id, 1)):
        sub.mkdir(parents=True, exist_ok=True)
    version.ref_pack_path = str(refs_dir.relative_to(layout.root)).replace("\\", "/")

    await db.commit()
    return character_to_out(await get_character(db, character.id))


async def update_character(db: AsyncSession, character_id: str, payload: CharacterUpdate) -> dict:
    c = await get_character(db, character_id)
    if c.status == CharacterStatus.ARCHIVED:
        raise CharacterServiceError("Cannot edit archived character")

    # Working version: retrain drafting if set, else unlocked drafting, else create new for ready edits
    version = _working_version(c)
    if version is None:
        raise CharacterServiceError("No version available")

    if c.status == CharacterStatus.READY and version.id == c.locked_version_id:
        # Edits to a locked character create a new drafting version (retrain track) for profile changes only
        # Profile-only edits on ready: update a new drafting version without demoting ready
        next_int = max(v.version_int for v in c.versions) + 1
        layout = get_layout()
        refs_dir = layout.refs_dir(c.id, next_int)
        version = CharacterVersion(
            character_id=c.id,
            version_int=next_int,
            status=VersionStatus.DRAFTING,
            appearance_json=dict(version.appearance_json or {}),
            personality_json=dict(version.personality_json or {}),
            boundaries_json=dict(version.boundaries_json or {}),
            speaking_style_json=dict(version.speaking_style_json or {}),
            marketing_voice_json=dict(version.marketing_voice_json or {}),
            niche_tags_json=list(version.niche_tags_json or []),
            trigger_word=version.trigger_word,
            pipeline_params_json=dict(version.pipeline_params_json or {}),
            prompt_contract_json=dict(version.prompt_contract_json or {}),
            safety_profile_json=dict(version.safety_profile_json or {}),
            ref_pack_path=str(refs_dir.relative_to(layout.root)).replace("\\", "/"),
            lora_path=None,
        )
        db.add(version)
        await db.flush()
        c.retrain_version_id = version.id
        for sub in (
            refs_dir,
            layout.lora_dir(c.id, next_int),
            layout.dataset_dir(c.id, next_int),
        ):
            sub.mkdir(parents=True, exist_ok=True)

    data = payload.model_dump(exclude_unset=True)
    if "display_name" in data and data["display_name"]:
        c.display_name = data["display_name"]
    for field in (
        "age_appearance_min",
        "age_appearance_band",
        "synthetic_confirmed",
        "not_real_person_attested",
        "attestation_text",
        "preferred_pipeline",
    ):
        if field in data and data[field] is not None:
            val = data[field]
            setattr(c, field, str(val) if field in ("age_appearance_band", "preferred_pipeline") else val)
    if "niche_tags" in data and data["niche_tags"] is not None:
        c.niche_tags_json = data["niche_tags"]
        version.niche_tags_json = data["niche_tags"]
    if "appearance" in data and data["appearance"] is not None:
        version.appearance_json = data["appearance"]
    if "personality" in data and data["personality"] is not None:
        version.personality_json = data["personality"]
    if "boundaries" in data and data["boundaries"] is not None:
        version.boundaries_json = data["boundaries"]
    if "speaking_style" in data and data["speaking_style"] is not None:
        version.speaking_style_json = data["speaking_style"]
    if "marketing_voice" in data and data["marketing_voice"] is not None:
        version.marketing_voice_json = data["marketing_voice"]
    if "trigger_word" in data and data["trigger_word"] is not None:
        version.trigger_word = data["trigger_word"]
    if "pipeline_params" in data and data["pipeline_params"] is not None:
        version.pipeline_params_json = data["pipeline_params"]

    contract = build_prompt_contract(
        appearance=version.appearance_json or {},
        boundaries=version.boundaries_json or {},
        trigger_word=version.trigger_word,
    )
    version.prompt_contract_json = contract.model_dump()
    version.safety_profile_json = {
        "age_appearance_min": c.age_appearance_min,
        "age_appearance_band": c.age_appearance_band,
        "synthetic_confirmed": c.synthetic_confirmed,
    }
    c.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return character_to_out(await get_character(db, character_id))


def _working_version(c: Character) -> CharacterVersion | None:
    if c.retrain_version_id:
        v = next((x for x in c.versions if x.id == c.retrain_version_id), None)
        if v:
            return v
    if c.locked_version_id:
        return next((x for x in c.versions if x.id == c.locked_version_id), None)
    if c.versions:
        return max(c.versions, key=lambda x: x.version_int)
    return None


async def mark_bootstrap(db: AsyncSession, character_id: str) -> dict:
    """draft → bootstrap after refs/seed are considered ready (manual advance for MVP)."""
    c = await get_character(db, character_id)
    if c.status not in (CharacterStatus.DRAFT, CharacterStatus.BOOTSTRAP):
        raise CharacterServiceError(f"Cannot bootstrap from status {c.status}")
    if not c.synthetic_confirmed or not c.not_real_person_attested:
        raise CharacterServiceError("Confirm synthetic + not-real-person before bootstrap")
    if c.age_appearance_min < 21:
        raise CharacterServiceError("age_appearance_min must be >= 21")
    c.status = CharacterStatus.BOOTSTRAP
    await db.commit()
    return character_to_out(await get_character(db, character_id))


async def lock_character(db: AsyncSession, character_id: str, payload: LockCharacterRequest) -> dict:
    c = await get_character(db, character_id)
    version = next((v for v in c.versions if v.id == payload.version_id), None)
    if not version:
        raise CharacterServiceError("Version not found", 404)
    if not payload.confirm_adult or not payload.confirm_synthetic or not payload.confirm_not_real_person:
        raise CharacterServiceError("All lock checklist confirmations are required")
    if not c.synthetic_confirmed or c.age_appearance_min < 21:
        raise CharacterServiceError("Character safety flags incomplete")
    lora_ok = False
    if version.lora_path:
        lp = get_layout().root / str(version.lora_path).replace("\\", "/")
        lora_ok = lp.is_file()
    if not lora_ok and not payload.allow_without_lora:
        raise CharacterServiceError(
            "Lock requires a registered LoRA file. Train and register weights, "
            "or set allow_without_lora for a dry-run lock (identity will drift)."
        )
    if c.locked_version_id and c.locked_version_id != version.id:
        old = next((v for v in c.versions if v.id == c.locked_version_id), None)
        if old:
            old.status = VersionStatus.SUPERSEDED
    version.status = VersionStatus.ACTIVE
    version.locked_at = datetime.now(timezone.utc)
    version.locked_by_attestation = payload.checklist_attestation
    c.locked_version_id = version.id
    c.retrain_version_id = None
    c.status = CharacterStatus.READY
    await db.commit()
    return character_to_out(await get_character(db, character_id))


async def archive_character(db: AsyncSession, character_id: str) -> dict:
    c = await get_character(db, character_id)
    c.status = CharacterStatus.ARCHIVED
    await db.commit()
    return character_to_out(await get_character(db, character_id))


def preview_prompts(c: Character, theme: str, **hints: str | None) -> dict:
    version = _working_version(c)
    if not version:
        raise CharacterServiceError("No version")
    contract = version.prompt_contract_json or build_prompt_contract(
        appearance=version.appearance_json or {},
        boundaries=version.boundaries_json or {},
        trigger_word=version.trigger_word,
    ).model_dump()
    positive, negative = render_flux_prompts(
        contract,
        theme=theme,
        outfit_hint=hints.get("outfit_hint"),
        pose_hint=hints.get("pose_hint"),
        location_hint=hints.get("location_hint"),
        extra_prompt=hints.get("extra_prompt"),
    )
    return {"positive": positive, "negative": negative, "contract": contract}
