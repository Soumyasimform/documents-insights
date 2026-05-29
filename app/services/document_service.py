from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import structlog
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException

from app.constants import RATE_LIMIT_MAX
from app.db.mongo import get_documents_collection
from app.messages import (
    ERR_DOCUMENT_NOT_FOUND,
    ERR_RATE_LIMIT_EXCEEDED,
    LOG_CACHE_HIT,
    LOG_DOCUMENT_CREATED,
    LOG_DUPLICATE_DOCUMENT_FOUND,
)
from app.models.document import DocumentCreateRequest, DocumentListResponse, DocumentResponse, DocumentStatus
from app.services import cache_service, rate_limiter

log = structlog.get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


async def create_document(request: DocumentCreateRequest) -> DocumentResponse:
    content_hash = _hash_content(request.content)

    # Dedup check: same user already has a non-failed record for this content — return it
    # Covers queued, processing, and completed — failed is intentionally excluded to allow retry
    existing = await get_documents_collection().find_one({
        "user_id": request.user_id,
        "content_hash": content_hash,
        "status": {"$in": [DocumentStatus.queued, DocumentStatus.processing, DocumentStatus.completed]},
    })
    if existing:
        log.info(LOG_DUPLICATE_DOCUMENT_FOUND, user_id=request.user_id,
                 document_id=str(existing["_id"]), status=existing["status"])
        return DocumentResponse.model_validate(existing)

    # Cross-user cache hit: another user's completed processing populated the cache —
    # create a new completed record for this user instantly (no queue slot consumed)
    cached = await cache_service.get_cached_summary(content_hash)
    if cached:
        log.info(LOG_CACHE_HIT, user_id=request.user_id, content_hash=content_hash)
        now = _now()
        doc = {
            "user_id": request.user_id,
            "title": request.title,
            "content": request.content,
            "content_hash": content_hash,
            "status": DocumentStatus.completed,
            "summary": cached,
            "error": None,
            "retry_count": 0,
            "available_at": now,
            "created_at": now,
            "updated_at": now,
            "processed_at": now,
        }
        result = await get_documents_collection().insert_one(doc)
        doc["_id"] = result.inserted_id
        return DocumentResponse.model_validate(doc)

    # Rate limit check
    allowed = await rate_limiter.check_and_reserve(request.user_id)
    if not allowed:
        raise HTTPException(status_code=429, detail=ERR_RATE_LIMIT_EXCEEDED.format(limit=RATE_LIMIT_MAX))

    now = _now()
    doc = {
        "user_id": request.user_id,
        "title": request.title,
        "content": request.content,
        "content_hash": content_hash,
        "status": DocumentStatus.queued,
        "summary": None,
        "error": None,
        "retry_count": 0,
        "available_at": now,
        "created_at": now,
        "updated_at": now,
        "processed_at": None,
    }
    result = await get_documents_collection().insert_one(doc)
    doc["_id"] = result.inserted_id
    log.info(LOG_DOCUMENT_CREATED, document_id=str(result.inserted_id), user_id=request.user_id)
    return DocumentResponse.model_validate(doc)


async def get_document(document_id: str) -> DocumentResponse:
    try:
        oid = ObjectId(document_id)
    except (InvalidId, Exception):
        raise HTTPException(status_code=404, detail=ERR_DOCUMENT_NOT_FOUND)

    doc = await get_documents_collection().find_one({"_id": oid})
    if doc is None:
        raise HTTPException(status_code=404, detail=ERR_DOCUMENT_NOT_FOUND)
    return DocumentResponse.model_validate(doc)


async def list_documents(
    user_id: str,
    page: int,
    page_size: int,
    status: DocumentStatus | None,
) -> DocumentListResponse:
    query: dict = {"user_id": user_id}
    if status is not None:
        query["status"] = status

    col = get_documents_collection()
    total = await col.count_documents(query)
    skip = (page - 1) * page_size
    cursor = col.find(query).sort("created_at", -1).skip(skip).limit(page_size)
    docs = await cursor.to_list(length=page_size)

    return DocumentListResponse(
        items=[DocumentResponse.model_validate(d) for d in docs],
        total=total,
        page=page,
        page_size=page_size,
    )
