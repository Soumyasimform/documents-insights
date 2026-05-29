from __future__ import annotations

import structlog
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ASCENDING, IndexModel

from app.config import settings
from app.constants import MONGO_COLLECTION_DOCUMENTS
from app.messages import (
    LOG_MONGODB_CLOSED,
    LOG_MONGODB_CONNECTED,
    LOG_MONGODB_INDEXES_CREATED,
)

log = structlog.get_logger(__name__)

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def get_client() -> AsyncIOMotorClient:
    if _client is None:
        raise RuntimeError("MongoDB client not initialized")
    return _client


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("MongoDB not initialized")
    return _db


def get_documents_collection() -> AsyncIOMotorCollection:
    return get_db()[MONGO_COLLECTION_DOCUMENTS]


async def init_mongo() -> None:
    global _client, _db
    _client = AsyncIOMotorClient(settings.mongodb_url)
    _db = _client[settings.mongodb_db_name]
    await init_indexes()
    log.info(LOG_MONGODB_CONNECTED, db=settings.mongodb_db_name)


async def close_mongo() -> None:
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
        log.info(LOG_MONGODB_CLOSED)


async def init_indexes() -> None:
    col = get_documents_collection()
    indexes = [
        IndexModel([("user_id", ASCENDING), ("status", ASCENDING)], background=True),
        IndexModel([("status", ASCENDING), ("created_at", ASCENDING)], background=True),
        IndexModel([("content_hash", ASCENDING)], sparse=True, background=True),
        IndexModel(
            [("status", ASCENDING), ("available_at", ASCENDING)],
            background=True,
            sparse=True,
        ),
        # Supports dedup check: find existing queued/processing doc by (user_id, content_hash)
        IndexModel([("user_id", ASCENDING), ("content_hash", ASCENDING)], background=True),
    ]
    await col.create_indexes(indexes)
    log.info(LOG_MONGODB_INDEXES_CREATED)


async def ping_mongo() -> bool:
    try:
        await get_client().admin.command("ping")
        return True
    except Exception:
        return False
