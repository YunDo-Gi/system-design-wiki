from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.limiter.base import Decision, Rule
from app.middleware import MAX_THROTTLE_MS, RateLimitMiddleware
from app.rules import RuleNode, Rules


def _make_app(rule: Rule, decision: Decision) -> FastAPI:
    """deny를 항상 반환하는 stub limiter로 app 구성."""

    class _StubLimiter:
        async def allow(self, key, r):
            return decision

    app = FastAPI()

    # 트리에 endpoint=shorten으로 rule 박기
    root = RuleNode()
    endpoint_node = RuleNode(rate_limit=rule)
    root.children[("endpoint", "shorten")] = endpoint_node
    app.state.rules = Rules(domain="knot", root=root)

    app.add_middleware(RateLimitMiddleware)

    # registry monkeypatch — get_limiter("X")가 stub 반환
    import app.limiter.registry as registry
    original = registry.get_limiter
    registry.get_limiter = lambda name: _StubLimiter()

    @app.post("/shorten", name="shorten")
    async def shorten(payload: dict):
        return {"code": "stub"}

    app._restore_registry = lambda: setattr(registry, "get_limiter", original)
    return app


@pytest.mark.asyncio
async def test_hard_mode_denies_with_429():
    rule = Rule(algorithm="sliding_window_log", unit="minute", requests_per_unit=10, mode="hard")
    decision = Decision(allowed=False, limit=10, remaining=0, retry_after=0.5)
    app = _make_app(rule, decision)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/shorten", json={"url": "x"})
        assert r.status_code == 429
        assert r.headers["x-ratelimit-limit"] == "10"
        assert r.headers["x-ratelimit-remaining"] == "0"
        assert "x-ratelimit-throttled" not in r.headers
    finally:
        app._restore_registry()


@pytest.mark.asyncio
async def test_soft_mode_throttles_with_200():
    rule = Rule(algorithm="sliding_window_log", unit="minute", requests_per_unit=10, mode="soft")
    decision = Decision(allowed=False, limit=10, remaining=0, retry_after=0.3)  # 300ms
    app = _make_app(rule, decision)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            start = time.perf_counter()
            r = await c.post("/shorten", json={"url": "x"})
            elapsed = time.perf_counter() - start
        assert r.status_code == 200
        assert r.headers["x-ratelimit-throttled"] == "true"
        assert int(r.headers["x-ratelimit-throttle-ms"]) == 300
        # 실제 sleep된 시간 검증 (관대한 하한)
        assert elapsed >= 0.25, f"throttle slept only {elapsed}s"
    finally:
        app._restore_registry()


@pytest.mark.asyncio
async def test_soft_mode_too_long_falls_back_to_hard():
    """retry_after가 MAX_THROTTLE_MS 초과면 429 fallback."""
    rule = Rule(algorithm="sliding_window_log", unit="minute", requests_per_unit=10, mode="soft")
    decision = Decision(allowed=False, limit=10, remaining=0, retry_after=(MAX_THROTTLE_MS / 1000) + 1)
    app = _make_app(rule, decision)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/shorten", json={"url": "x"})
        assert r.status_code == 429
        assert "x-ratelimit-throttled" not in r.headers
    finally:
        app._restore_registry()
