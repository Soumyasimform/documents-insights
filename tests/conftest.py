from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient


@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


@pytest_asyncio.fixture
async def mock_mongo_db():
    client = AsyncMongoMockClient()
    db = client["test_document_insights"]
    yield db
    client.close()


@pytest_asyncio.fixture
async def mock_redis():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


@pytest_asyncio.fixture
async def app_client(mock_mongo_db, mock_redis) -> AsyncGenerator[AsyncClient, None]:
    import app.db.mongo as mongo_module
    import app.db.redis_client as redis_module

    original_db = mongo_module._db
    original_client = mongo_module._client
    original_redis = redis_module._redis

    mongo_module._db = mock_mongo_db
    mongo_module._client = AsyncMongoMockClient()
    redis_module._redis = mock_redis

    # Patch init functions so lifespan doesn't create new real connections
    with (
        patch("app.main.init_mongo", new_callable=AsyncMock),
        patch("app.main.close_mongo", new_callable=AsyncMock),
        patch("app.main.init_redis", new_callable=AsyncMock),
        patch("app.main.close_redis", new_callable=AsyncMock),
        patch("app.db.mongo.init_indexes", new_callable=AsyncMock),
    ):
        from app.main import create_app

        application = create_app(skip_worker=True)
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://test"
        ) as client:
            yield client

    mongo_module._db = original_db
    mongo_module._client = original_client
    redis_module._redis = original_redis
