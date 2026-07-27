"""Domain enums shared across API, worker, and UI contracts."""

from __future__ import annotations

from enum import StrEnum


class CharacterStatus(StrEnum):
    DRAFT = "draft"
    BOOTSTRAP = "bootstrap"
    TRAINING = "training"
    READY = "ready"
    ARCHIVED = "archived"


class VersionStatus(StrEnum):
    DRAFTING = "drafting"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    FAILED = "failed"
    DISCARDED = "discarded"


class JobType(StrEnum):
    SEED_GALLERY = "seed_gallery"
    STILL_BATCH = "still_batch"
    LORA_TRAIN = "lora_train"
    REF_EMBED = "ref_embed"
    VALIDATION_SHEET = "validation_sheet"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobItemStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class AssetKind(StrEnum):
    STILL = "still"
    VIDEO = "video"
    CAPTION_DOC = "caption_doc"


class AssetDecision(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class BriefStatus(StrEnum):
    DRAFT = "draft"
    GENERATING = "generating"
    COMPLETED = "completed"


class AgeAppearanceBand(StrEnum):
    MID_20S = "mid-20s"
    LATE_20S = "late-20s"
    THIRTIES = "30s"
    FORTIES = "40s"
    FIFTIES_PLUS = "50s+"


class Pipeline(StrEnum):
    FLUX = "flux"
    SDXL = "sdxl"  # post-MVP
