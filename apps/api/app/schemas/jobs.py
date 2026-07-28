from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from instantimpact_common.schemas import BriefItem


class SeedGalleryRequest(BaseModel):
    count: int = Field(default=8, ge=1, le=40)
    themes: list[str] = Field(default_factory=lambda: ["portrait", "casual_bedroom", "glamour"])
    aspect_ratio: str = "4:5"


class StillBatchRequest(BaseModel):
    items: list[BriefItem]
    aspect_ratio: str = "4:5"
    seed_policy: str = "random"
    title: str | None = None


class ContentBriefCreate(BaseModel):
    title: str
    items: list[BriefItem]
    aspect_ratio: str = "4:5"
    seed_policy: str = "random"


class ContentBriefOut(BaseModel):
    id: str
    character_id: str
    title: str
    status: str
    items: list[Any]
    aspect_ratio: str
    seed_policy: str
    created_at: datetime

    model_config = {"from_attributes": True}


class JobItemOut(BaseModel):
    id: str
    item_index: int
    status: str
    asset_id: str | None
    error_message: str | None
    consistency_score: float | None
    request: dict[str, Any]

    model_config = {"from_attributes": True}


class JobOut(BaseModel):
    id: str
    type: str
    status: str
    character_id: str | None
    character_version_id: str | None
    brief_id: str | None
    error_code: str | None
    error_message: str | None
    cancel_requested: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    items: list[JobItemOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class AssetOut(BaseModel):
    id: str
    character_id: str
    character_version_id: str
    job_id: str | None
    kind: str
    path: str
    thumb_path: str | None
    width: int | None
    height: int | None
    seed: int | None
    prompt_positive: str | None
    decision: str
    consistency_score: float | None
    meta: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class AssetDecisionRequest(BaseModel):
    decision: str  # approved | rejected | pending
    score: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = None


class AssetDeleteResponse(BaseModel):
    id: str
    deleted: bool = True
    character_id: str
    files_removed: int = 0


class AssetBulkDeleteRequest(BaseModel):
    asset_ids: list[str] | None = None
    decision: str | None = Field(
        default=None,
        description="If set (e.g. rejected), delete all assets with this decision",
    )
    delete_files: bool = True


class AssetBulkDeleteResponse(BaseModel):
    character_id: str
    deleted: int
    files_removed: int = 0


class GpuStatusOut(BaseModel):
    locked: bool
    holder_job_id: str | None = None
    holder_type: str | None = None
    message: str = "idle"
    mock_generation: bool = True
    comfy_enabled: bool = False
    comfy_healthy: bool | None = None
