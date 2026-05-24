from __future__ import annotations

import httpx

from client.base import RateLimitedResult, ShortenResult


class NaiveClient:
    """httpx wrapper. 캐시·backoff 없음. 429 받으면 RateLimitedResult 반환."""

    def __init__(self, base_url: str, api_key: str = "", user_tier: str = "default") -> None:
        self._client = httpx.AsyncClient(base_url=base_url)
        self._headers = {"x-api-key": api_key, "x-user-tier": user_tier}

    async def shorten(self, url: str) -> ShortenResult | RateLimitedResult:
        r = await self._client.post(
            "/shorten",
            json={"url": url},
            headers={**self._headers, "content-type": "application/json"},
        )
        if r.status_code == 429:
            return RateLimitedResult(
                retry_after=float(r.headers.get("x-ratelimit-retry-after", 0)),
                limit=int(r.headers.get("x-ratelimit-limit", 0)),
            )
        body = r.json()
        return ShortenResult(
            code=body["code"],
            limit=int(r.headers.get("x-ratelimit-limit", 0)),
            remaining=int(r.headers.get("x-ratelimit-remaining", 0)),
            throttled=r.headers.get("x-ratelimit-throttled") == "true",
            throttle_ms=int(r.headers.get("x-ratelimit-throttle-ms", 0)),
        )

    async def aclose(self) -> None:
        await self._client.aclose()
