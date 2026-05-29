from __future__ import annotations

import hashlib
import json

import pytest


@pytest.mark.asyncio
async def test_submit_document_returns_201(app_client):
    resp = await app_client.post("/documents", json={
        "user_id": "user1",
        "title": "My Doc",
        "content": "Hello world this is unique content abc123",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "queued"
    assert "id" in body
    assert body["user_id"] == "user1"


@pytest.mark.asyncio
async def test_submit_document_validates_empty_content(app_client):
    resp = await app_client.post("/documents", json={
        "user_id": "user1",
        "title": "Test",
        "content": "",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_document_validates_missing_fields(app_client):
    resp = await app_client.post("/documents", json={"user_id": "user1"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_document_returns_queued(app_client):
    create_resp = await app_client.post("/documents", json={
        "user_id": "user2",
        "title": "Poll Test",
        "content": "Content for polling test xyzqrs",
    })
    assert create_resp.status_code == 201
    doc_id = create_resp.json()["id"]

    get_resp = await app_client.get(f"/documents/{doc_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "queued"
    assert get_resp.json()["id"] == doc_id


@pytest.mark.asyncio
async def test_get_document_404_for_unknown_id(app_client):
    resp = await app_client.get("/documents/000000000000000000000000")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_document_404_for_invalid_id(app_client):
    resp = await app_client.get("/documents/not-a-valid-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cache_hit_returns_completed_immediately(app_client, mock_redis):
    content = "Cached content body that will be hashed and stored"
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    summary = {
        "summary": "Cached summary",
        "word_count": 9,
        "key_topics": ["cached", "content"],
        "sentiment": "neutral",
    }
    await mock_redis.setex(f"content_cache:{content_hash}", 86400, json.dumps(summary))

    resp = await app_client.post("/documents", json={
        "user_id": "user_cache",
        "title": "Cached Doc",
        "content": content,
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "completed"
    assert body["summary"]["summary"] == "Cached summary"


@pytest.mark.asyncio
async def test_cache_hit_creates_new_document_id(app_client, mock_redis):
    content = "Another piece of content for caching uniqueness check"
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    summary = {"summary": "s", "word_count": 8, "key_topics": [], "sentiment": "neutral"}
    await mock_redis.setex(f"content_cache:{content_hash}", 86400, json.dumps(summary))

    r1 = await app_client.post("/documents", json={"user_id": "u1", "title": "A", "content": content})
    r2 = await app_client.post("/documents", json={"user_id": "u2", "title": "B", "content": content})

    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]


@pytest.mark.asyncio
async def test_same_user_same_content_queued_returns_existing_document(app_client):
    """Scenario: same user submits identical content while first doc is still queued.
    Expected: second submission returns the existing queued document — no new record created."""
    content = "Duplicate content submitted while queued unique xyz987"

    r1 = await app_client.post("/documents", json={"user_id": "dedup_user", "title": "First", "content": content})
    assert r1.status_code == 201
    assert r1.json()["status"] == "queued"
    doc_id_first = r1.json()["id"]

    r2 = await app_client.post("/documents", json={"user_id": "dedup_user", "title": "Second", "content": content})
    assert r2.status_code == 201
    assert r2.json()["id"] == doc_id_first  # same document returned
    assert r2.json()["status"] == "queued"

    # Confirm only one record exists in the DB
    list_resp = await app_client.get("/users/dedup_user/documents")
    assert list_resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_different_users_same_content_queued_creates_separate_documents(app_client):
    """Scenario: two different users submit the same content — both get their own document."""
    content = "Shared content different users unique abc456"

    r1 = await app_client.post("/documents", json={"user_id": "user_alpha", "title": "Doc", "content": content})
    r2 = await app_client.post("/documents", json={"user_id": "user_beta", "title": "Doc", "content": content})

    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]  # separate documents
    assert r1.json()["user_id"] == "user_alpha"
    assert r2.json()["user_id"] == "user_beta"


@pytest.mark.asyncio
async def test_same_user_same_content_after_completion_returns_existing_record(app_client, mock_redis):
    """Scenario: same user resubmits content that is already completed (MongoDB has a completed doc).
    Expected: existing completed document returned — no new record created."""
    content = "Completed content resubmitted unique qrs321"
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    summary = {"summary": "done", "word_count": 3, "key_topics": [], "sentiment": "neutral"}
    await mock_redis.setex(f"content_cache:{content_hash}", 86400, json.dumps(summary))

    # First submission hits cache → creates completed record for this user
    r1 = await app_client.post("/documents", json={"user_id": "replay_user", "title": "A", "content": content})
    assert r1.status_code == 201
    assert r1.json()["status"] == "completed"

    # Second submission → MongoDB dedup check finds existing completed doc → returns same record
    r2 = await app_client.post("/documents", json={"user_id": "replay_user", "title": "B", "content": content})
    assert r2.status_code == 201
    assert r2.json()["id"] == r1.json()["id"]  # same document returned, no duplicate

    # Confirm only one record exists for this user
    list_resp = await app_client.get("/users/replay_user/documents")
    assert list_resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_different_users_same_completed_content_get_separate_records(app_client, mock_redis):
    """Scenario: different users submit same content after it has been completed.
    Expected: each user gets their own completed record (cross-user cache hit path)."""
    content = "Cross user content unique mno654"
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    summary = {"summary": "cross", "word_count": 4, "key_topics": [], "sentiment": "neutral"}
    await mock_redis.setex(f"content_cache:{content_hash}", 86400, json.dumps(summary))

    r1 = await app_client.post("/documents", json={"user_id": "cross_user_1", "title": "Doc", "content": content})
    r2 = await app_client.post("/documents", json={"user_id": "cross_user_2", "title": "Doc", "content": content})

    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]  # separate records per user
    assert r1.json()["status"] == "completed"
    assert r2.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_list_user_documents(app_client):
    for i in range(3):
        await app_client.post("/documents", json={
            "user_id": "list_user",
            "title": f"Doc {i}",
            "content": f"Content body number {i} with unique words abcdefg{i}",
        })

    resp = await app_client.get("/users/list_user/documents")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3
    assert body["page"] == 1


@pytest.mark.asyncio
async def test_list_user_documents_pagination(app_client):
    # Use 3 unique users each submitting 1 doc so no rate limit is hit;
    # we test pagination on a single user with 3 docs using page_size=2
    for i in range(3):
        await app_client.post("/documents", json={
            "user_id": "page_user",
            "title": f"P{i}",
            "content": f"Paginated content body item {i} unique wordset zyx{i}",
        })

    r1 = await app_client.get("/users/page_user/documents?page=1&page_size=2")
    assert r1.status_code == 200
    assert len(r1.json()["items"]) == 2
    assert r1.json()["total"] == 3

    r2 = await app_client.get("/users/page_user/documents?page=2&page_size=2")
    assert r2.status_code == 200
    assert len(r2.json()["items"]) == 1
    assert r2.json()["total"] == 3


@pytest.mark.asyncio
async def test_list_user_documents_status_filter(app_client):
    resp = await app_client.get("/users/list_user/documents?status=queued")
    assert resp.status_code == 200
    for item in resp.json()["items"]:
        assert item["status"] == "queued"


@pytest.mark.asyncio
async def test_list_unknown_user_returns_empty(app_client):
    resp = await app_client.get("/users/ghost_user_xyz/documents")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    assert resp.json()["items"] == []
