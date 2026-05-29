from __future__ import annotations

import asyncio

import structlog

from app.constants import CACHE_TTL_SECONDS, CONTENT_LOCK_TTL_SECONDS, CONTENT_LOCK_WAIT_SECONDS
from app.db import redis_client
from app.db.redis_client import RedisUnavailableError
from app.messages import LOG_CACHE_GET_UNAVAILABLE

log = structlog.get_logger(__name__)


async def get_cached_summary(content_hash: str) -> dict | None:
    try:
        return await redis_client.cache_get(content_hash)
    except RedisUnavailableError:
        log.warning(LOG_CACHE_GET_UNAVAILABLE, content_hash=content_hash)
        return None


async def store_summary(content_hash: str, summary: dict) -> None:
    await redis_client.cache_set(content_hash, summary, CACHE_TTL_SECONDS)


async def try_acquire_processing_lock(content_hash: str) -> bool:
    return await redis_client.try_acquire_content_lock(content_hash, CONTENT_LOCK_TTL_SECONDS)


async def wait_for_cached_summary(content_hash: str) -> dict | None:
    """Poll cache until a summary appears or CONTENT_LOCK_WAIT_SECONDS passes."""
    elapsed = 0
    while elapsed < CONTENT_LOCK_WAIT_SECONDS:
        await asyncio.sleep(5)
        elapsed += 5
        result = await get_cached_summary(content_hash)
        if result is not None:
            return result
    return None


