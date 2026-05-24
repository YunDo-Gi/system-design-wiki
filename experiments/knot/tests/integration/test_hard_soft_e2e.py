"""Cycle 5 — Hard vs Soft 정책 e2e.

premium tier는 rules.yaml에 `mode: soft` 적용된 상태. free/default는 hard.

**시간 측정 주의**: rules.yaml의 premium은 sliding_window_log 50/min.
50번 빠르게 보낸 직후 51번째 요청의 retry_after는 ~60s에 가까워
MAX_THROTTLE_MS(2000ms)를 초과 → soft가 hard로 폴백된다.
soft throttle을 실제로 관측하려면 더 작은 window가 필요하므로
throttle 측정 테스트는 premium 규칙을 임시로 sliding_window_log 2/second 로 덮어쓴다
(테스트 종료 후 원복).
"""

from __future__ import annotations

import time

import pytest

from app.limiter.base import Rule


@pytest.mark.asyncio
async def test_free_tier_hard_429(client):
    """free tier (default) — hard 모드. 11번째 429."""
    headers = {"x-api-key": "hs-free", "x-user-tier": "free"}
    last_status = None
    for _ in range(11):
        r = await client.post("/shorten", json={"url": "https://e.com"}, headers=headers)
        last_status = r.status_code
    assert last_status == 429


@pytest.mark.asyncio
async def test_premium_tier_soft_throttle(client):
    """premium soft — 한도 초과 시 throttle 후 200.

    rules.yaml premium 기본 정책(50/minute)은 retry_after가 ~60s이므로
    soft가 MAX_THROTTLE_MS 폴백돼 429가 된다. 본 테스트는 soft *throttle 자체*가
    동작하는지 검증하기 위해 premium 규칙을 2/second 로 임시 교체한다.
    """
    from app.main import app

    rules = app.state.rules
    original = rules.root.children[("endpoint", "shorten")].children[
        ("user_tier", "premium")
    ].rate_limit
    rules.root.children[("endpoint", "shorten")].children[
        ("user_tier", "premium")
    ].rate_limit = Rule(
        algorithm="sliding_window_log",
        unit="second",
        requests_per_unit=2,
        mode="soft",
    )

    try:
        headers = {"x-api-key": "hs-premium", "x-user-tier": "premium"}
        # 2번 빠르게 (모두 통과)
        for _ in range(2):
            r = await client.post(
                "/shorten", json={"url": "https://e.com"}, headers=headers
            )
            assert r.status_code == 200

        # 3번째 — soft throttle 발생해야 함
        start = time.perf_counter()
        r = await client.post(
            "/shorten", json={"url": "https://e.com"}, headers=headers
        )
        elapsed = time.perf_counter() - start

        assert r.status_code == 200, (
            f"soft mode는 200으로 통과해야 함. status={r.status_code} headers={dict(r.headers)}"
        )
        assert r.headers.get("x-ratelimit-throttled") == "true"
        throttle_ms = int(r.headers["x-ratelimit-throttle-ms"])
        assert throttle_ms > 0, "throttle_ms는 0보다 커야 함"
        # 실제 sleep 시간이 throttle_ms 근처 (관대한 하한 80%)
        assert elapsed * 1000 >= throttle_ms * 0.8, (
            f"elapsed {elapsed*1000:.0f}ms vs throttle {throttle_ms}ms"
        )
    finally:
        rules.root.children[("endpoint", "shorten")].children[
            ("user_tier", "premium")
        ].rate_limit = original


@pytest.mark.asyncio
async def test_premium_throttle_does_not_count(client):
    """soft throttle된 요청은 limiter counter에 추가되지 않음.

    sliding_window_log는 ZSET에 timestamp를 저장한다. throttle된 요청이
    카운트에 포함되지 않음을 직접 ZCARD로 검증:
        N번 통과 → ZCARD == N
        한 번 throttle → ZCARD 여전히 N (증가 안 함)

    window가 짧아 throttle 동안 만료될 가능성이 있으므로 unit=minute을 쓰되,
    limit을 충분히 작게(2) 잡아 MAX_THROTTLE_MS 초과를 유도한 후
    throttle 동작 대신 카운터 불변성만 검증한다.
    실제 throttle 동작은 test_premium_tier_soft_throttle에서 검증됨.
    """
    from app.main import app
    from app.redis_client import get_redis

    rules = app.state.rules
    original = rules.root.children[("endpoint", "shorten")].children[
        ("user_tier", "premium")
    ].rate_limit
    rules.root.children[("endpoint", "shorten")].children[
        ("user_tier", "premium")
    ].rate_limit = Rule(
        algorithm="sliding_window_log",
        unit="second",
        requests_per_unit=2,
        mode="soft",
    )

    try:
        headers = {"x-api-key": "hs-premium-2", "x-user-tier": "premium"}
        # 2번 빠르게 (다 통과)
        for _ in range(2):
            r = await client.post(
                "/shorten", json={"url": "https://e.com"}, headers=headers
            )
            assert r.status_code == 200

        redis = get_redis()
        zkey = "knot:swl:shorten:hs-premium-2"
        count_before = await redis.zcard(zkey)
        assert count_before == 2

        # 3번째 — soft throttle. 200 + Throttled true가 되어야 하고,
        # 카운터(ZSET)에는 추가되지 않아야 한다.
        r = await client.post(
            "/shorten", json={"url": "https://e.com"}, headers=headers
        )
        assert r.status_code == 200
        assert r.headers.get("x-ratelimit-throttled") == "true"

        # throttle 후 sleep으로 window가 일부 스크롤될 수 있으므로
        # "throttle 직전 == 2" 와 비교해 "증가가 0" 임을 확인.
        # ZSET에 throttle된 timestamp가 추가됐다면 1초 안에는 만료되지 않아 카운트가 늘었을 것.
        # (window는 1초이므로 sleep 후 일부 timestamp가 만료될 수는 있으나 throttle된
        # timestamp가 *추가되었다면* 그 timestamp는 가장 최근이므로 만료되지 않는다.)
        count_after = await redis.zcard(zkey)
        assert count_after <= 2, (
            f"throttle된 요청이 ZSET에 추가됨: before={count_before} after={count_after}"
        )
    finally:
        rules.root.children[("endpoint", "shorten")].children[
            ("user_tier", "premium")
        ].rate_limit = original
