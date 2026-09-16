from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from instantimpact_common.enums import AgeAppearanceBand, CharacterStatus, Pipeline
from instantimpact_common.schemas import (
    AppearanceProfile,
    BoundariesProfile,
    PersonalityProfile,
    PipelineParams,
    SpeakingStyle,
)


class CharacterCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    slug: str | None = None
    age_appearance_min: int = Field(default=21, ge=21)
    age_appearance_band: AgeAppearanceBand = AgeAppearanceBand.MID_20S
    synthetic_confirmed: bool = False
    not_real_person_attested: bool = False
    attestation_text: str | None = None
    niche_tags: list[str] = Field(default_factory=list)
    preferred_pipeline: Pipeline = Pipeline.FLUX
    appearance: AppearanceProfile = Field(default_factory=AppearanceProfile)
    personality: PersonalityProfile = Field(default_factory=PersonalityProfile)
    boundaries: BoundariesProfile = Field(default_factory=BoundariesProfile)
    speaking_style: SpeakingStyle = Field(default_factory=SpeakingStyle)
    trigger_word: str | None = None

    @field_validator("age_appearance_min")
    @classmethod
    def adult_only(cls, v: int) -> int:
        if v < 21:
            raise ValueError("age_appearance_min must be >= 21")
        return v


class RandomCharacterRequest(BaseModel):
    """Options for POST /api/characters/random."""

    seed: int | None = Field(
        default=None,
        description="Optional RNG seed for reproducible random personas",
    )
    auto_attest: bool = Field(
        default=False,
        description="Pre-check synthetic + not-real-person (required for generation)",
    )
    auto_bootstrap: bool = Field(
        default=False,
        description="Advance draft → bootstrap so seed gallery / stills are allowed",
    )


class BuildDatasetRequest(BaseModel):
    decision: str = Field(default="approved", description="Asset decision filter")
    min_images: int = Field(default=4, ge=1, le=200)


class RegisterLoraRequest(BaseModel):
    source_path: str = Field(
        min_length=1,
        description="Absolute path to .safetensors on nemesis, or path under data/",
    )
    strength: float = Field(default=0.85, ge=0.0, le=2.0)
    install_to_comfy: bool = True


class CharacterUpdate(BaseModel):
    display_name: str | None = None
    age_appearance_min: int | None = Field(default=None, ge=21)
    age_appearance_band: AgeAppearanceBand | None = None
    synthetic_confirmed: bool | None = None
    not_real_person_attested: bool | None = None
    attestation_text: str | None = None
    niche_tags: list[str] | None = None
    preferred_pipeline: Pipeline | None = None
    appearance: AppearanceProfile | None = None
    personality: PersonalityProfile | None = None
    boundaries: BoundariesProfile | None = None
    speaking_style: SpeakingStyle | None = None
    trigger_word: str | None = None
    pipeline_params: PipelineParams | None = None


class CharacterVersionOut(BaseModel):
    id: str
    character_id: str
    version_int: int
    status: str
    appearance: dict[str, Any]
    personality: dict[str, Any]
    boundaries: dict[str, Any]
    speaking_style: dict[str, Any]
    niche_tags: list[str]
    trigger_word: str | None
    lora_path: str | None
    ref_pack_path: str | None
    prompt_contract: dict[str, Any]
    pipeline_params: dict[str, Any]
    locked_at: datetime | None

    model_config = {"from_attributes": True}


class CharacterOut(BaseModel):
    id: str
    slug: str
    display_name: str
    status: CharacterStatus | str
    preferred_pipeline: str
    age_appearance_min: int
    age_appearance_band: str
    synthetic_confirmed: bool
    not_real_person_attested: bool
    attestation_text: str | None
    locked_version_id: str | None
    retrain_version_id: str | None
    niche_tags: list[str]
    created_at: datetime
    updated_at: datetime
    current_version: CharacterVersionOut | None = None
    preview_thumb: str | None = None

    model_config = {"from_attributes": True}


class PromptPreviewRequest(BaseModel):
    theme: str = "portrait"
    outfit_hint: str | None = None
    pose_hint: str | None = None
    location_hint: str | None = None
    extra_prompt: str | None = None


class PromptPreviewResponse(BaseModel):
    positive: str
    negative: str
    contract: dict[str, Any]


class LockCharacterRequest(BaseModel):
    version_id: str
    checklist_attestation: str = Field(min_length=10)
    confirm_adult: bool
    confirm_synthetic: bool
    confirm_not_real_person: bool
    allow_without_lora: bool = Field(
        default=False,
        description="Dry-run lock only. Production lock requires a registered LoRA file.",
    )


class TransitionResponse(BaseModel):
    character: CharacterOut
    message: str
