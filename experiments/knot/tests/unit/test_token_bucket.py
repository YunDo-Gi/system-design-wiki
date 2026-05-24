from __future__ import annotations

import pytest
from freezegun import freeze_time

from app.limiter.base import Rule


@pytest.fixture
def rule():
    # capacity=10, rate=5 tokens/sec
    return Rule(algorithm="token_bucket", unit="second", requests_per_unit=5, burst=10)


@pytest.fixture
async def limiter(monkeypatch):
    """fakeredis-backed TokenBucket."""
    import fakeredis.aioredis
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)

    # Patch get_redis to return fake
    import app.redis_client
    monkeypatch.setattr(app.redis_client, "_client", fake)

    from app.limiter.token_bucket import TokenBucket
    return TokenBucket()


@pytest.mark.asyncio
async def test_first_call_initializes_full_bucket(limiter, rule):
    d = await limiter.allow("knot:redirect:1.2.3.4", rule)
    assert d.allowed is True
    assert d.limit == 10
    assert d.remaining == 9  # 10 - 1 cost


@pytest.mark.asyncio
async def test_burst_absorbs_capacity_then_denies(limiter, rule):
    with freeze_time("2026-05-24 12:00:00"):
        for _ in range(10):
            d = await limiter.allow("knot:redirect:user-a", rule)
            assert d.allowed is True
        # 11번째는 denied
        d = await limiter.allow("knot:redirect:user-a", rule)
        assert d.allowed is False
        assert d.remaining == 0
        assert d.retry_after > 0


@pytest.mark.asyncio
async def test_refill_after_time_advance(limiter, rule):
    with freeze_time("2026-05-24 12:00:00") as ft:
        # 버킷 비우기
        for _ in range(10):
            await limiter.allow("knot:redirect:user-b", rule)
        denied = await limiter.allow("knot:redirect:user-b", rule)
        assert denied.allowed is False

        # 1초 후 → 5 토큰 회복
        ft.tick(1.0)
        d = await limiter.allow("knot:redirect:user-b", rule)
        assert d.allowed is True
        # 1초에 5 회복했고 1개 차감 → remaining ≈ 4
        assert d.remaining in (3, 4)


@pytest.mark.asyncio
async def test_overfill_capped_at_capacity(limiter, rule):
    with freeze_time("2026-05-24 12:00:00") as ft:
        # 1회 호출 (last_refill 기록)
        await limiter.allow("knot:redirect:user-c", rule)
        # 1시간 후 (이론상 18000 토큰 회복) → capacity로 capped
        ft.tick(3600)
        d = await limiter.allow("knot:redirect:user-c", rule)
        assert d.allowed is True
        assert d.remaining == 9  # capacity=10, 1개 차감


@pytest.mark.asyncio
async def test_identities_have_separate_buckets(limiter, rule):
    with freeze_time("2026-05-24 12:00:00"):
        for _ in range(10):
            await limiter.allow("knot:redirect:user-x", rule)
        # user-x는 비었지만 user-y는 풀
        d = await limiter.allow("knot:redirect:user-y", rule)
        assert d.allowed is True
        assert d.remaining == 9
