from __future__ import annotations

import pytest


def _unique_doc(user_id: str, idx: int) -> dict:
    return {
        "user_id": user_id,
        "title": f"Doc {idx}",
        "content": f"Unique content for rate limit test item {idx} with extra words {idx * 999}",
    }


@pytest.mark.asyncio
async def test_fourth_submission_rejected_with_429(app_client):
    for i in range(3):
        r = await app_client.post("/documents", json=_unique_doc("throttled", i))
        assert r.status_code == 201, f"Expected 201 on submission {i}, got {r.status_code}"

    r4 = await app_client.post("/documents", json=_unique_doc("throttled", 99))
    assert r4.status_code == 429
    assert "Rate limit exceeded" in r4.json()["detail"]


@pytest.mark.asyncio
async def test_rate_limit_is_per_user(app_client):
    for i in range(3):
        r = await app_client.post("/documents", json=_unique_doc("user_a", i))
        assert r.status_code == 201

    # Different user should not be affected
    r = await app_client.post("/documents", json=_unique_doc("user_b", 0))
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_cache_hit_does_not_consume_rate_limit_slot(app_client, mock_redis):
    import hashlib
    import json

    content = "Shared cached content for rate limit test"
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    summary = {"summary": "s", "word_count": 7, "key_topics": [], "sentiment": "neutral"}
    await mock_redis.setex(f"content_cache:{content_hash}", 86400, json.dumps(summary))

    # Use 3 slots for non-cached docs
    for i in range(3):
        r = await app_client.post("/documents", json=_unique_doc("rl_cache_user", i))
        assert r.status_code == 201

    # Cache hit should still succeed (does not consume a slot)
    r = await app_client.post("/documents", json={
        "user_id": "rl_cache_user",
        "title": "Cached",
        "content": content,
    })
    assert r.status_code == 201
    assert r.json()["status"] == "completed"
