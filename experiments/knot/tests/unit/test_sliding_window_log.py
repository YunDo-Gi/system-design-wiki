# experiments/knot/tests/unit/test_sliding_window_log.py
from __future__ import annotations

import pytest
from freezegun import freeze_time

from app.limiter.base import Rule


@pytest.fixture
async def limiter(monkeypatch):
    import fakeredis.aioredis
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    import app.redis_client
    monkeypatch.setattr(app.redis_client, "_client", fake)
    from app.limiter.sliding_window_log import SlidingWindowLog
    return SlidingWindowLog()


@pytest.mark.asyncio
async def test_basic_pass_then_deny(limiter):
    rule = Rule(algorithm="sliding_window_log", unit="minute", requests_per_unit=5)
    with freeze_time("2026-05-24 12:00:00"):
        for i in range(5):
            d = await limiter.allow("knot:test:user-a", rule)
            assert d.allowed is True
            assert d.remaining == 4 - i
        d = await limiter.allow("knot:test:user-a", rule)
        assert d.allowed is False
        assert d.remaining == 0
        assert d.retry_after > 0


@pytest.mark.asyncio
async def test_no_boundary_burst(limiter):
    """sliding window는 fixed window의 경계 burst를 해결."""
    rule = Rule(algorithm="sliding_window_log", unit="minute", requests_per_unit=5)
    # 12:00:59에 5번 (cycle 2 fixed_window라면 다 통과)
    with freeze_time("2026-05-24 12:00:59") as ft:
        for _ in range(5):
            d = await limiter.allow("knot:test:user-b", rule)
            assert d.allowed is True

        # 1초 후 (12:01:00) — sliding window: 직전 60초(12:00:00~12:01:00)에 이미 5개 존재 → 거부
        ft.tick(1.0)
        d = await limiter.allow("knot:test:user-b", rule)
        assert d.allowed is False, "sliding window는 경계에서 추가 통과 막아야 함"


@pytest.mark.asyncio
async def test_window_slides_continuously(limiter):
    """오래된 timestamp가 윈도우 밖으로 나가면 새 요청 통과."""
    rule = Rule(algorithm="sliding_window_log", unit="second", requests_per_unit=3)
    # 1초 윈도우에 3개 채움
    with freeze_time("2026-05-24 12:00:00") as ft:
        for _ in range(3):
            await limiter.allow("knot:test:user-c", rule)
        # 4번째 거부
        d = await limiter.allow("knot:test:user-c", rule)
        assert d.allowed is False

        # 1.1초 후 — 첫 3개가 모두 윈도우 밖 → 새 요청 통과
        ft.tick(1.1)
        d = await limiter.allow("knot:test:user-c", rule)
        assert d.allowed is True


@pytest.mark.asyncio
async def test_retry_after_accurate(limiter):
    """retry_after_ms = (oldest_ts + window - now) — 정확한 시각."""
    rule = Rule(algorithm="sliding_window_log", unit="second", requests_per_unit=2)
    with freeze_time("2026-05-24 12:00:00.000000") as ft:
        await limiter.allow("knot:test:user-d", rule)   # ts=12:00:00
        ft.tick(0.3)
        await limiter.allow("knot:test:user-d", rule)   # ts=12:00:00.3
        ft.tick(0.1)
        # 12:00:00.4 시점 — limit=2 소진
        d = await limiter.allow("knot:test:user-d", rule)
        assert d.allowed is False
        # oldest=12:00:00, window=1s, now=12:00:00.4 → retry_after = 12:00:01 - 12:00:00.4 = 0.6s = 600ms
        assert 550 <= d.retry_after * 1000 <= 700, f"retry_after={d.retry_after*1000}ms"
