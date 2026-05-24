# experiments/knot/tests/integration/test_sliding_window_log_redis.py
import asyncio

import pytest


@pytest.mark.asyncio
async def test_shorten_burst_throttled(client):
    """shorten 분당 10 — 11회 연속이면 마지막 deny."""
    headers = {"x-api-key": "burst-test-c3"}
    statuses = []
    for _ in range(11):
        r = await client.post("/shorten", json={"url": "https://example.com"}, headers=headers)
        statuses.append(r.status_code)
    passed = sum(1 for s in statuses if s == 200)
    denied = sum(1 for s in statuses if s == 429)
    assert passed == 10
    assert denied == 1


@pytest.mark.asyncio
async def test_race_condition_atomic_zset(client):
    """50 동시 POST (limit=10) → 정확히 10 통과 (ZSET + Lua atomicity)."""
    headers = {"x-api-key": "race-test-c3"}

    async def hit():
        r = await client.post("/shorten", json={"url": "https://example.com"}, headers=headers)
        return r.status_code

    results = await asyncio.gather(*[hit() for _ in range(50)])
    passed = sum(1 for s in results if s == 200)
    denied = sum(1 for s in results if s == 429)
    assert passed == 10, f"passed={passed} — ZSET atomic 위반 의심"
    assert passed + denied == 50


@pytest.mark.asyncio
async def test_identity_isolation_shorten(client):
    """다른 API key는 별도 ZSET."""
    for _ in range(10):
        await client.post("/shorten", json={"url": "https://example.com"}, headers={"x-api-key": "user-x-c3"})

    r = await client.post("/shorten", json={"url": "https://example.com"}, headers={"x-api-key": "user-y-c3"})
    assert r.status_code == 200
    assert r.headers["x-ratelimit-remaining"] == "9"
