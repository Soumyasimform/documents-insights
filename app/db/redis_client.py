from __future__ import annotations

import json

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import settings
from app.constants import (
    RATE_LIMIT_MAX,
    REDIS_CONTENT_CACHE_PREFIX,
    REDIS_CONTENT_LOCK_PREFIX,
    REDIS_RATE_LIMIT_PREFIX,
)
from app.messages import (
    LOG_REDIS_CACHE_GET_FAILED,
    LOG_REDIS_CACHE_SET_FAILED,
    LOG_REDIS_CLOSED,
    LOG_REDIS_CONNECTED,
    LOG_REDIS_LOCK_FAILED,
    LOG_REDIS_RATE_LIMIT_DECR_FAILED,
    LOG_REDIS_RATE_LIMIT_UNAVAILABLE,
    LOG_REDIS_UNAVAILABLE_AT_STARTUP,
)

log = structlog.get_logger(__name__)

_redis: Redis | None = None

# Atomic check-and-increment: returns new count or -1 if limit reached
_RATE_LIMIT_SCRIPT = """
local current = redis.call('GET', KEYS[1])
if current == false then current = 0 else current = tonumber(current) end
if current >= tonumber(ARGV[1]) then return -1 end
redis.call('INCR', KEYS[1])
return current + 1
"""

# Acquire a lock via SET NX EX; returns 1 if acquired, 0 if already held
_SETNX_LOCK_SCRIPT = """
local result = redis.call('SET', KEYS[1], 1, 'NX', 'EX', ARGV[1])
if result then return 1 else return 0 end
"""


class RedisUnavailableError(Exception):
    pass


def get_redis() -> Redis:
    if _redis is None:
        raise RuntimeError("Redis client not initialized")
    return _redis


async def init_redis() -> None:
    global _redis
    _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await _redis.ping()
        log.info(LOG_REDIS_CONNECTED)
    except RedisError as exc:
        log.warning(LOG_REDIS_UNAVAILABLE_AT_STARTUP, error=str(exc))


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None
        log.info(LOG_REDIS_CLOSED)


async def ping_redis() -> bool:
    try:
        return bool(await get_redis().ping())
    except Exception:
        return False


async def rate_limit_check_incr(user_id: str) -> int:
    """Returns new counter value, or -1 if limit exceeded. Raises RedisUnavailableError on connection failure."""
    try:
        result = await get_redis().eval(
            _RATE_LIMIT_SCRIPT,
            1,
            f"{REDIS_RATE_LIMIT_PREFIX}:{user_id}",
            str(RATE_LIMIT_MAX),
        )
        return int(result)
    except RedisError as exc:
        log.warning(LOG_REDIS_RATE_LIMIT_UNAVAILABLE, error=str(exc))
        raise RedisUnavailableError from exc


async def rate_limit_decr(user_id: str) -> None:
    """Decrement active job counter. Logs but does not raise on Redis failure."""
    try:
        key = f"{REDIS_RATE_LIMIT_PREFIX}:{user_id}"
        r = get_redis()
        current = await r.get(key)
        if current is not None and int(current) > 0:
            await r.decr(key)
    except RedisError as exc:
        log.warning(LOG_REDIS_RATE_LIMIT_DECR_FAILED, user_id=user_id, error=str(exc))


async def cache_get(content_hash: str) -> dict | None:
    try:
        value = await get_redis().get(f"{REDIS_CONTENT_CACHE_PREFIX}:{content_hash}")
        if value:
            return json.loads(value)
        return None
    except RedisError as exc:
        log.warning(LOG_REDIS_CACHE_GET_FAILED, error=str(exc))
        raise RedisUnavailableError from exc


async def cache_set(content_hash: str, summary: dict, ttl: int) -> None:
    try:
        await get_redis().setex(
            f"{REDIS_CONTENT_CACHE_PREFIX}:{content_hash}",
            ttl,
            json.dumps(summary),
        )
    except RedisError as exc:
        log.warning(LOG_REDIS_CACHE_SET_FAILED, error=str(exc))


async def try_acquire_content_lock(content_hash: str, ttl: int) -> bool:
    """Returns True if this caller acquired the processing lock for content_hash."""
    try:
        result = await get_redis().eval(
            _SETNX_LOCK_SCRIPT,
            1,
            f"{REDIS_CONTENT_LOCK_PREFIX}:{content_hash}",
            str(ttl),
        )
        return int(result) == 1
    except RedisError as exc:
        log.warning(LOG_REDIS_LOCK_FAILED, error=str(exc))
        return True  # fail-open: let the caller proceed


