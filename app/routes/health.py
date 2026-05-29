from fastapi import APIRouter

from app.constants import HEALTH_STATUS_DEGRADED, HEALTH_STATUS_OK
from app.db.mongo import ping_mongo
from app.db.redis_client import ping_redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    mongo_ok = await ping_mongo()
    redis_ok = await ping_redis()
    status = HEALTH_STATUS_OK if mongo_ok and redis_ok else HEALTH_STATUS_DEGRADED
    return {"status": status, "mongo": mongo_ok, "redis": redis_ok}
