from __future__ import annotations

import pytest
from freezegun import freeze_time

from app.limiter.base import Rule


@pytest.fixture
def rule():
    # 5 req per 10 seconds
    return Rule(algorithm="fixed_window", unit="second", requests_per_unit=5)


@pytest.fixture
async def limiter(monkeypatch):
    import fakeredis.aioredis
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    import app.redis_client
    monkeypatch.setattr(app.redis_client, "_client", fake)
    from app.limiter.fixed_window import FixedWindow
    return FixedWindow()


@pytest.mark.asyncio
async def test_basic_pass_then_deny(limiter, rule):
    """5번 통과 + 6번째 거부."""
    rule_per_min = Rule(algorithm="fixed_window", unit="minute", requests_per_unit=5)
    with freeze_time("2026-05-24 12:00:30"):
        for i in range(5):
            d = await limiter.allow("knot:test:user-a", rule_per_min)
            assert d.allowed is True, f"req {i+1} should pass"
            assert d.remaining == 4 - i
        # 6th
        d = await limiter.allow("knot:test:user-a", rule_per_min)
        assert d.allowed is False
        assert d.remaining == 0
        assert d.retry_after > 0


@pytest.mark.asyncio
async def test_boundary_burst_demonstrates_2x(limiter, rule):
    """ch04 §"fixed window 한계": 윈도우 경계 전후로 5+5 = 10 통과 (의도 2x).

    분 단위 limit=5에서 1분의 마지막 1초에 5번 + 다음 분 첫 1초에 5번 → 2초간 10 통과.
    의도된 정책 (분당 5)의 2배가 단기적으로 통과되는 fixed window의 한계.
    """
    rule_per_min = Rule(algorithm="fixed_window", unit="minute", requests_per_unit=5)

    # 12:00:59 — 1분의 마지막 직전, 5개 burst
    with freeze_time("2026-05-24 12:00:59") as ft:
        for _ in range(5):
            d = await limiter.allow("knot:test:user-b", rule_per_min)
            assert d.allowed is True
        # 6번째는 deny (이 윈도우 한도 소진)
        d = await limiter.allow("knot:test:user-b", rule_per_min)
        assert d.allowed is False

        # 1초 흐름 → 다음 분(12:01:00)
        ft.tick(1.0)
        # 새 윈도우: 5개 더 통과
        for _ in range(5):
            d = await limiter.allow("knot:test:user-b", rule_per_min)
            assert d.allowed is True
        # 6번째 deny
        d = await limiter.allow("knot:test:user-b", rule_per_min)
        assert d.allowed is False

    # 결론: 12:00:59 ~ 12:01:00 (2초 구간)에 10 통과 — 의도(분당 5)의 2배


@pytest.mark.asyncio
async def test_window_isolation_no_carryover(limiter, rule):
    """한 윈도우 소진 후 다음 윈도우는 fresh — carryover 없음."""
    rule_per_min = Rule(algorithm="fixed_window", unit="minute", requests_per_unit=5)
    with freeze_time("2026-05-24 12:00:00") as ft:
        for _ in range(5):
            await limiter.allow("knot:test:user-c", rule_per_min)
        # 다음 분으로
        ft.tick(60.0)
        d = await limiter.allow("knot:test:user-c", rule_per_min)
        assert d.allowed is True
        assert d.remaining == 4  # 5 - 1 (fresh window)
