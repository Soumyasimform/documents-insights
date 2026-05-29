from __future__ import annotations

import structlog

from app.constants import RATE_LIMIT_MAX
from app.db import redis_client
from app.db.mongo import get_documents_collection
from app.db.redis_client import RedisUnavailableError
from app.messages import LOG_RATE_LIMIT_EXCEEDED, LOG_RATE_LIMIT_REDIS_FALLBACK
from app.models.document import DocumentStatus

log = structlog.get_logger(__name__)


async def check_and_reserve(user_id: str) -> bool:
    """Returns True if submission is allowed and slot is reserved. False → 429."""
    try:
        result = await redis_client.rate_limit_check_incr(user_id)
        allowed = result != -1
        if not allowed:
            log.info(LOG_RATE_LIMIT_EXCEEDED, user_id=user_id, source="redis")
        return allowed
    except RedisUnavailableError:
        log.warning(LOG_RATE_LIMIT_REDIS_FALLBACK, user_id=user_id)
        count = await get_documents_collection().count_documents(
            {"user_id": user_id, "status": {"$in": [DocumentStatus.queued, DocumentStatus.processing]}}
        )
        allowed = count < RATE_LIMIT_MAX
        if not allowed:
            log.info(LOG_RATE_LIMIT_EXCEEDED, user_id=user_id, source="mongodb_fallback")
        return allowed


async def release(user_id: str) -> None:
    """Decrement the active job counter. Called on completion or failure."""
    await redis_client.rate_limit_decr(user_id)
