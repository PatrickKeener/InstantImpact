from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    preferred_pipeline: Mapped[str] = mapped_column(String(32), default="flux")
    age_appearance_min: Mapped[int] = mapped_column(Integer, default=21)
    age_appearance_band: Mapped[str] = mapped_column(String(32), default="mid-20s")
    synthetic_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    not_real_person_attested: Mapped[bool] = mapped_column(Boolean, default=False)
    attestation_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    locked_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    retrain_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    niche_tags_json: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    versions: Mapped[list[CharacterVersion]] = relationship(
        back_populates="character", cascade="all, delete-orphan"
    )


class CharacterVersion(Base):
    __tablename__ = "character_versions"
    __table_args__ = (UniqueConstraint("character_id", "version_int", name="uq_char_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    character_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    version_int: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="drafting")
    appearance_json: Mapped[dict] = mapped_column(JSON, default=dict)
    personality_json: Mapped[dict] = mapped_column(JSON, default=dict)
    boundaries_json: Mapped[dict] = mapped_column(JSON, default=dict)
    speaking_style_json: Mapped[dict] = mapped_column(JSON, default=dict)
    niche_tags_json: Mapped[list] = mapped_column(JSON, default=list)
    trigger_word: Mapped[str | None] = mapped_column(String(80), nullable=True)
    lora_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    lora_strength_default: Mapped[float] = mapped_column(Float, default=0.85)
    pipeline_params_json: Mapped[dict] = mapped_column(JSON, default=dict)
    ref_pack_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_checkpoint_id: Mapped[str] = mapped_column(String(120), default="flux_dev_placeholder")
    prompt_contract_json: Mapped[dict] = mapped_column(JSON, default=dict)
    safety_profile_json: Mapped[dict] = mapped_column(JSON, default=dict)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by_attestation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    character: Mapped[Character] = relationship(back_populates="versions")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    type: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    character_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    character_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    brief_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    request_json: Mapped[dict] = mapped_column(JSON, default=dict)
    request_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_on_item_failure: Mapped[bool] = mapped_column(Boolean, default=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list[JobItem]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class JobItem(Base):
    __tablename__ = "job_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    item_index: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    request_json: Mapped[dict] = mapped_column(JSON, default=dict)
    asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    consistency_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    job: Mapped[Job] = relationship(back_populates="items")


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    character_id: Mapped[str] = mapped_column(String(36), index=True)
    character_version_id: Mapped[str] = mapped_column(String(36), index=True)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    job_item_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), default="still")
    path: Mapped[str] = mapped_column(Text)
    thumb_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_positive: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_negative: Mapped[str | None] = mapped_column(Text, nullable=True)
    pipeline: Mapped[str] = mapped_column(String(32), default="flux")
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)
    decision: Mapped[str] = mapped_column(String(32), default="pending")
    consistency_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AssetRating(Base):
    __tablename__ = "asset_ratings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assets.id", ondelete="CASCADE"), index=True
    )
    score: Mapped[int] = mapped_column(Integer)
    tags_json: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ContentBrief(Base):
    __tablename__ = "content_briefs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    character_id: Mapped[str] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="draft")
    items_json: Mapped[list] = mapped_column(JSON, default=list)
    seed_policy: Mapped[str] = mapped_column(String(32), default="random")
    aspect_ratio: Mapped[str] = mapped_column(String(16), default="4:5")
    pipeline_override: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class ApprovedSet(Base):
    __tablename__ = "approved_sets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    character_id: Mapped[str] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(200))
    manifest_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    export_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_export_approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ApprovedSetItem(Base):
    __tablename__ = "approved_set_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    set_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("approved_sets.id", ondelete="CASCADE"), index=True
    )
    asset_id: Mapped[str] = mapped_column(String(36), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    caption_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class Product(Base):
    """Commercial product reference for ad-style stills (separate from character face refs)."""

    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), index=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    primary_path: Mapped[str] = mapped_column(Text)
    thumb_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value_json: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
