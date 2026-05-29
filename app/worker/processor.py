from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from pymongo import ASCENDING, ReturnDocument

from app.constants import MAX_RETRIES, RETRY_BACKOFF_BASE, WORKER_POLL_INTERVAL
from app.db.mongo import get_documents_collection
from app.messages import (
    LOG_CONCURRENT_CACHE_WAIT_TIMED_OUT,
    LOG_PROCESSING_COMPLETED,
    LOG_PROCESSING_COMPLETED_FROM_CACHE,
    LOG_PROCESSING_FAILED_PERMANENTLY,
    LOG_PROCESSING_FAILED_WILL_RETRY,
    LOG_PROCESSING_STARTED,
    LOG_WAITING_FOR_CONCURRENT_DUPLICATE,
    LOG_WORKER_STARTED,
    LOG_WORKER_STOPPED,
    LOG_WORKER_UNEXPECTED_ERROR,
)
from app.models.document import DocumentStatus
from app.services import cache_service, rate_limiter
from app.services.summarizer import ProcessingError, generate_summary

log = structlog.get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def claim_next_document() -> dict | None:
    """Atomically claim one queued document. Returns None if nothing available."""
    doc = await get_documents_collection().find_one_and_update(
        {
            "status": DocumentStatus.queued,
            "available_at": {"$lte": _now()},
        },
        {"$set": {"status": DocumentStatus.processing, "updated_at": _now()}},
        sort=[("created_at", ASCENDING)],
        return_document=ReturnDocument.AFTER,
    )
    return doc


async def process_document(doc: dict, worker_id: int) -> None:
    doc_id = doc["_id"]
    user_id = doc["user_id"]
    content_hash = doc["content_hash"]

    bound_log = log.bind(worker_id=worker_id, document_id=str(doc_id), user_id=user_id)
    bound_log.info(LOG_PROCESSING_STARTED)

    col = get_documents_collection()

    # SETNX lock: if another worker is processing the same content hash (different user),
    # wait for it to populate the cache rather than doing duplicate work.
    lock_acquired = await cache_service.try_acquire_processing_lock(content_hash)
    if not lock_acquired:
        bound_log.info(LOG_WAITING_FOR_CONCURRENT_DUPLICATE)
        cached = await cache_service.wait_for_cached_summary(content_hash)
        if cached:
            await col.update_one(
                {"_id": doc_id},
                {"$set": {
                    "status": DocumentStatus.completed,
                    "summary": cached,
                    "processed_at": _now(),
                    "updated_at": _now(),
                }},
            )
            await rate_limiter.release(user_id)
            bound_log.info(LOG_PROCESSING_COMPLETED_FROM_CACHE)
            return
        # Cache never populated (other worker failed) — proceed independently
        bound_log.warning(LOG_CONCURRENT_CACHE_WAIT_TIMED_OUT)

    try:
        summary = await generate_summary(doc["title"], doc["content"])
    except ProcessingError as exc:
        await _handle_failure(doc, str(exc), bound_log)
        return
    except asyncio.CancelledError:
        # Worker is shutting down; reset to queued so another worker can pick it up
        await col.update_one(
            {"_id": doc_id},
            {"$set": {"status": DocumentStatus.queued, "updated_at": _now()}},
        )
        raise

    await col.update_one(
        {"_id": doc_id},
        {"$set": {
            "status": DocumentStatus.completed,
            "summary": summary,
            "processed_at": _now(),
            "updated_at": _now(),
        }},
    )
    await cache_service.store_summary(content_hash, summary)
    await rate_limiter.release(user_id)
    bound_log.info(LOG_PROCESSING_COMPLETED)


async def _handle_failure(doc: dict, error: str, bound_log: structlog.BoundLogger) -> None:
    doc_id = doc["_id"]
    user_id = doc["user_id"]
    retry_count = doc.get("retry_count", 0)
    col = get_documents_collection()

    if retry_count < MAX_RETRIES:
        backoff_seconds = RETRY_BACKOFF_BASE * (2 ** retry_count)
        available_at = _now() + timedelta(seconds=backoff_seconds)
        await col.update_one(
            {"_id": doc_id},
            {"$set": {
                "status": DocumentStatus.queued,
                "retry_count": retry_count + 1,
                "available_at": available_at,
                "error": error,
                "updated_at": _now(),
            }},
        )
        bound_log.warning(LOG_PROCESSING_FAILED_WILL_RETRY, retry_count=retry_count + 1, backoff_seconds=backoff_seconds)
    else:
        await col.update_one(
            {"_id": doc_id},
            {"$set": {
                "status": DocumentStatus.failed,
                "error": error,
                "updated_at": _now(),
            }},
        )
        await rate_limiter.release(user_id)
        bound_log.error(LOG_PROCESSING_FAILED_PERMANENTLY, error=error)


async def worker_loop(worker_id: int) -> None:
    log.info(LOG_WORKER_STARTED, worker_id=worker_id)
    try:
        while True:
            try:
                doc = await claim_next_document()
                if doc is None:
                    await asyncio.sleep(WORKER_POLL_INTERVAL)
                    continue
                await process_document(doc, worker_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error(LOG_WORKER_UNEXPECTED_ERROR, worker_id=worker_id, error=str(exc), exc_info=True)
                await asyncio.sleep(WORKER_POLL_INTERVAL)
    except asyncio.CancelledError:
        log.info(LOG_WORKER_STOPPED, worker_id=worker_id)
