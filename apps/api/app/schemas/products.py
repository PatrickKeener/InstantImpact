from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ProductOut(BaseModel):
    id: str
    name: str
    slug: str
    description: str | None = None
    brand: str | None = None
    primary_path: str
    thumb_path: str | None = None
    sha256: str = ""
    width: int | None = None
    height: int | None = None
    meta: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    brand: str | None = Field(default=None, max_length=120)
