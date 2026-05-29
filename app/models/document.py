from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class DocumentStatus(StrEnum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class DocumentCreateRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    title: str = Field(..., min_length=1, max_length=512)
    content: str = Field(..., min_length=1, max_length=100_000)

    @field_validator("user_id", "title", "content", mode="before")
    @classmethod
    def strip_whitespace(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip()
        return v


class SummaryResult(BaseModel):
    summary: str
    word_count: int
    key_topics: list[str]
    sentiment: str


class DocumentResponse(BaseModel):
    id: str
    user_id: str
    title: str
    content_hash: str
    status: DocumentStatus
    summary: SummaryResult | None = None
    error: str | None = None
    retry_count: int = 0
    created_at: datetime
    updated_at: datetime
    processed_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def coerce_id(cls, data: Any) -> Any:
        if isinstance(data, dict) and "_id" in data:
            data["id"] = str(data.pop("_id"))
        return data


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int
