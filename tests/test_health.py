from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_ok(app_client):
    resp = await app_client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("ok", "degraded")
    assert "mongo" in body
    assert "redis" in body


@pytest.mark.asyncio
async def test_health_structure(app_client):
    resp = await app_client.get("/health")
    body = resp.json()
    assert isinstance(body["mongo"], bool)
    assert isinstance(body["redis"], bool)
