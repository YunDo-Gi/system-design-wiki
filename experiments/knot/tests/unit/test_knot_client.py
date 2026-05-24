from __future__ import annotations

import httpx
import pytest
import respx
from freezegun import freeze_time

from client.naive import NaiveClient
from client.sdk import KnotClient, CACHE_TTL_S


@pytest.fixture
def mock_route():
    with respx.mock(base_url="http://test") as router:
        yield router


@pytest.mark.asyncio
async def test_naive_shorten_returns_response(mock_route):
    mock_route.post("/shorten").mock(return_value=httpx.Response(
        200, json={"code": "abc123"},
        headers={"x-ratelimit-limit": "10", "x-ratelimit-remaining": "9"},
    ))
    client = NaiveClient(base_url="http://test", api_key="k")
    result = await client.shorten("https://e.com")
    assert result.code == "abc123"
    assert result.limit == 10
    assert result.remaining == 9
    await client.aclose()


@pytest.mark.asyncio
async def test_sdk_cache_hit_skips_server(mock_route):
    route = mock_route.post("/shorten").mock(return_value=httpx.Response(
        200, json={"code": "abc123"},
        headers={"x-ratelimit-limit": "10", "x-ratelimit-remaining": "9"},
    ))
    client = KnotClient(base_url="http://test")
    # 첫 호출 — 서버 호출
    r1 = await client.shorten("https://e.com")
    assert r1.cached is False
    assert route.call_count == 1
    # 두 번째 호출 — 캐시 히트, 서버 호출 X
    r2 = await client.shorten("https://e.com")
    assert r2.cached is True
    assert r2.code == "abc123"
    assert route.call_count == 1     # 여전히 1
    assert client.cache_hits == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_sdk_cache_expires_after_ttl(mock_route):
    route = mock_route.post("/shorten").mock(return_value=httpx.Response(
        200, json={"code": "abc123"},
        headers={"x-ratelimit-limit": "10", "x-ratelimit-remaining": "9"},
    ))
    client = KnotClient(base_url="http://test")
    with freeze_time("2026-05-25 12:00:00") as ft:
        await client.shorten("https://e.com")
        assert route.call_count == 1
        # TTL 직전엔 캐시
        ft.tick(CACHE_TTL_S - 1)
        r = await client.shorten("https://e.com")
        assert r.cached is True
        assert route.call_count == 1
        # TTL 지나면 다시 서버 호출
        ft.tick(2)
        r = await client.shorten("https://e.com")
        assert r.cached is False
        assert route.call_count == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_sdk_backoff_on_429(mock_route):
    """첫 응답 429 → backoff 후 200 → 정상 결과 반환."""
    responses = [
        httpx.Response(429, headers={"x-ratelimit-retry-after": "0.01", "x-ratelimit-limit": "10"}),
        httpx.Response(200, json={"code": "after-retry"},
                       headers={"x-ratelimit-limit": "10", "x-ratelimit-remaining": "9"}),
    ]
    mock_route.post("/shorten").mock(side_effect=responses)

    client = KnotClient(base_url="http://test")
    result = await client.shorten("https://e.com")
    # backoff 후 두 번째 응답이 200이라 ShortenResult 받음
    assert hasattr(result, "code")
    assert result.code == "after-retry"
    assert client.backoff_waits == 1
    await client.aclose()
