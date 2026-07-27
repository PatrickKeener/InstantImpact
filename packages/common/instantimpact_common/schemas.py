"""Pydantic schemas for character profiles and job payloads."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from instantimpact_common.enums import AgeAppearanceBand, Pipeline


class AppearanceProfile(BaseModel):
    """Structured appearance — compiled to Flux prompts by prompt_engine."""

    ethnicity_hint: str | None = None
    skin_tone: str | None = None
    face_shape: str | None = None
    eye_color: str | None = None
    eye_shape: str | None = None
    hair_color: str | None = None
    hair_style: str | None = None
    hair_length: str | None = None
    body_type: str | None = None
    height_hint: str | None = None
    distinguishing_features: list[str] = Field(default_factory=list)
    style_keywords: list[str] = Field(default_factory=list)
    makeup_style: str | None = None
    typical_wardrobe: list[str] = Field(default_factory=list)
    freeform_notes: str | None = None


class PersonalityProfile(BaseModel):
    traits: list[str] = Field(default_factory=list)
    tone: str | None = None
    energy: str | None = None
    humor: str | None = None
    interests: list[str] = Field(default_factory=list)
    catchphrases: list[str] = Field(default_factory=list)
    bio_short: str | None = None


class SpeakingStyle(BaseModel):
    formality: str | None = None  # casual | warm | playful | direct
    emoji_use: str | None = None  # none | light | heavy
    vocabulary: str | None = None
    example_lines: list[str] = Field(default_factory=list)


class BoundariesProfile(BaseModel):
    """Hard bans become negative prompt fragments and enqueue deny checks."""

    hard_bans: list[str] = Field(default_factory=list)
    soft_limits: list[str] = Field(default_factory=list)
    content_allowed: list[str] = Field(default_factory=list)
    notes: str | None = None


class SafetyConfirmations(BaseModel):
    synthetic_confirmed: bool = False
    age_appearance_min: int = Field(default=21, ge=21)
    age_appearance_band: AgeAppearanceBand = AgeAppearanceBand.MID_20S
    not_real_person_attested: bool = False
    attestation_text: str | None = None

    @field_validator("age_appearance_min")
    @classmethod
    def must_be_adult(cls, v: int) -> int:
        if v < 21:
            raise ValueError("age_appearance_min must be >= 21")
        return v


class FluxPipelineParams(BaseModel):
    lora_strength: float = 0.85
    ip_adapter_strength: float = 0.6
    pulid_strength: float = 0.7
    steps: int = 28
    cfg: float = 3.5
    width: int = 1024
    height: int = 1280


class PipelineParams(BaseModel):
    flux: FluxPipelineParams = Field(default_factory=FluxPipelineParams)


class PromptContract(BaseModel):
    """Structured contract stored on character_versions; renderers produce strings."""

    subject_tokens: list[str] = Field(default_factory=list)
    appearance_tokens: list[str] = Field(default_factory=list)
    style_tokens: list[str] = Field(default_factory=list)
    quality_tokens: list[str] = Field(default_factory=list)
    negative_tokens: list[str] = Field(default_factory=list)
    trigger_word: str | None = None
    pipeline: Pipeline = Pipeline.FLUX
    raw_notes: str | None = None


class BriefItem(BaseModel):
    type: str = "still"  # still only in MVP; video rejected
    count: int = Field(default=1, ge=1, le=100)
    theme: str = "portrait"
    outfit_hint: str | None = None
    pose_hint: str | None = None
    location_hint: str | None = None
    extra_prompt: str | None = None


class StillUnitRequest(BaseModel):
    """Per-image work unit written into jobs/{id}/request.json items."""

    item_index: int
    seed: int | None = None
    theme: str = "portrait"
    outfit_hint: str | None = None
    pose_hint: str | None = None
    location_hint: str | None = None
    extra_prompt: str | None = None
    aspect_ratio: str = "4:5"
    preset: str = "still_production"


class JobRequestSnapshot(BaseModel):
    """Immutable FS snapshot at jobs/{job_id}/request.json — workers never open SQLite."""

    job_id: str
    type: str
    character_id: str
    character_version_id: str | None = None
    locked_version_id: str | None = None
    pipeline: str = "flux"
    trigger_word: str | None = None
    lora_path: str | None = None
    ref_pack_path: str | None = None
    prompt_contract: dict[str, Any] = Field(default_factory=dict)
    pipeline_params: dict[str, Any] = Field(default_factory=dict)
    boundaries: dict[str, Any] = Field(default_factory=dict)
    appearance: dict[str, Any] = Field(default_factory=dict)
    items: list[StillUnitRequest] = Field(default_factory=list)
    resume_on_item_failure: bool = True
    mock: bool = False
    meta: dict[str, Any] = Field(default_factory=dict)


class JobEvent(BaseModel):
    """Progress event on Redis bus → API → WebSocket."""

    job_id: str
    event: str  # queued|running|item_done|item_failed|progress|completed|failed|cancelled
    item_index: int | None = None
    asset_id: str | None = None
    thumbnail_path: str | None = None
    consistency_score: float | None = None
    message: str | None = None
    progress: float | None = None  # 0.0–1.0
    error_code: str | None = None
