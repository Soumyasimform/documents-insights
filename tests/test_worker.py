from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId


def _queued_doc(user_id: str = "worker_user") -> dict:
    now = datetime.now(timezone.utc)
    return {
        "_id": ObjectId(),
        "user_id": user_id,
        "title": "Test Doc",
        "content": "Some content for worker test",
        "content_hash": "abc123hash",
        "status": "queued",
        "summary": None,
        "error": None,
        "retry_count": 0,
        "available_at": now,
        "created_at": now,
        "updated_at": now,
        "processed_at": None,
    }


@pytest.mark.asyncio
async def test_claim_next_document(mock_mongo_db, mock_redis):
    import app.db.mongo as mongo_module
    import app.db.redis_client as redis_module

    original_db = mongo_module._db
    original_redis = redis_module._redis
    mongo_module._db = mock_mongo_db
    redis_module._redis = mock_redis

    try:
        col = mock_mongo_db["documents"]
        doc = _queued_doc()
        await col.insert_one(doc)

        from app.worker.processor import claim_next_document

        claimed = await claim_next_document()
        assert claimed is not None
        assert claimed["status"] == "processing"
        assert claimed["_id"] == doc["_id"]
    finally:
        mongo_module._db = original_db
        redis_module._redis = original_redis


@pytest.mark.asyncio
async def test_no_double_claim(mock_mongo_db, mock_redis):
    """Two concurrent workers cannot both claim the same document."""
    import app.db.mongo as mongo_module
    import app.db.redis_client as redis_module

    original_db = mongo_module._db
    original_redis = redis_module._redis
    mongo_module._db = mock_mongo_db
    redis_module._redis = mock_redis

    try:
        col = mock_mongo_db["documents"]
        doc = _queued_doc()
        await col.insert_one(doc)

        from app.worker.processor import claim_next_document

        results = await asyncio.gather(
            claim_next_document(),
            claim_next_document(),
        )
        claimed = [r for r in results if r is not None]
        assert len(claimed) == 1
    finally:
        mongo_module._db = original_db
        redis_module._redis = original_redis


@pytest.mark.asyncio
async def test_worker_processes_to_completed(mock_mongo_db, mock_redis):
    import app.db.mongo as mongo_module
    import app.db.redis_client as redis_module

    original_db = mongo_module._db
    original_redis = redis_module._redis
    mongo_module._db = mock_mongo_db
    redis_module._redis = mock_redis

    try:
        col = mock_mongo_db["documents"]
        doc = _queued_doc()
        await col.insert_one(doc)

        mock_summary = {
            "summary": "Test summary",
            "word_count": 5,
            "key_topics": ["content"],
            "sentiment": "neutral",
        }

        with (
            patch("app.worker.processor.generate_summary", new_callable=AsyncMock, return_value=mock_summary),
            patch("app.worker.processor.cache_service.try_acquire_processing_lock", new_callable=AsyncMock, return_value=True),
            patch("app.worker.processor.cache_service.store_summary", new_callable=AsyncMock),
            patch("app.worker.processor.rate_limiter.release", new_callable=AsyncMock),
        ):
            from app.worker.processor import process_document
            await process_document(doc, worker_id=0)

        updated = await col.find_one({"_id": doc["_id"]})
        assert updated["status"] == "completed"
        assert updated["summary"] == mock_summary
    finally:
        mongo_module._db = original_db
        redis_module._redis = original_redis


@pytest.mark.asyncio
async def test_worker_retries_on_failure(mock_mongo_db, mock_redis):
    import app.db.mongo as mongo_module
    import app.db.redis_client as redis_module
    from app.services.summarizer import ProcessingError

    original_db = mongo_module._db
    original_redis = redis_module._redis
    mongo_module._db = mock_mongo_db
    redis_module._redis = mock_redis

    try:
        col = mock_mongo_db["documents"]
        doc = _queued_doc()
        await col.insert_one(doc)

        with (
            patch("app.worker.processor.generate_summary", new_callable=AsyncMock, side_effect=ProcessingError("fail")),
            patch("app.worker.processor.cache_service.try_acquire_processing_lock", new_callable=AsyncMock, return_value=True),
        ):
            from app.worker.processor import process_document
            await process_document(doc, worker_id=0)

        updated = await col.find_one({"_id": doc["_id"]})
        assert updated["status"] == "queued"
        assert updated["retry_count"] == 1
        assert updated["error"] == "fail"
    finally:
        mongo_module._db = original_db
        redis_module._redis = original_redis


@pytest.mark.asyncio
async def test_worker_marks_failed_after_max_retries(mock_mongo_db, mock_redis):
    import app.db.mongo as mongo_module
    import app.db.redis_client as redis_module
    from app.services.summarizer import ProcessingError

    original_db = mongo_module._db
    original_redis = redis_module._redis
    mongo_module._db = mock_mongo_db
    redis_module._redis = mock_redis

    try:
        col = mock_mongo_db["documents"]
        doc = _queued_doc()
        doc["retry_count"] = 3  # already at max
        await col.insert_one(doc)

        with (
            patch("app.worker.processor.generate_summary", new_callable=AsyncMock, side_effect=ProcessingError("final fail")),
            patch("app.worker.processor.cache_service.try_acquire_processing_lock", new_callable=AsyncMock, return_value=True),
            patch("app.worker.processor.rate_limiter.release", new_callable=AsyncMock),
        ):
            from app.worker.processor import process_document
            await process_document(doc, worker_id=0)

        updated = await col.find_one({"_id": doc["_id"]})
        assert updated["status"] == "failed"
        assert updated["error"] == "final fail"
    finally:
        mongo_module._db = original_db
        redis_module._redis = original_redis
