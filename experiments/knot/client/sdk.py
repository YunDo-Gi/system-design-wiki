from __future__ import annotations

import asyncio
import time

import httpx

from client.base import RateLimitedResult, ShortenResult

CACHE_TTL_S = 5 * 60       # 5분
MAX_ATTEMPTS = 4
MAX_BACKOFF_S = 60
BASE_BACKOFF_S = 1


class KnotClient:
    def __init__(self, base_url: str, api_key: str = "", user_tier: str = "default") -> None:
        self._client = httpx.AsyncClient(base_url=base_url)
        self._headers = {"x-api-key": api_key, "x-user-tier": user_tier}
        self._cache: dict[str, tuple[ShortenResult, float]] = {}

        # 관측 가능 메트릭
        self.cache_hits = 0
        self.server_calls = 0
        self.backoff_waits = 0

    async def shorten(self, url: str) -> ShortenResult | RateLimitedResult:
        # 권고 ① 캐시
        if url in self._cache:
            result, expires_at = self._cache[url]
            if time.time() < expires_at:
                self.cache_hits += 1
                cached_result = ShortenResult(
                    code=result.code,
                    limit=result.limit,
                    remaining=result.remaining,
                    cached=True,
                )
                return cached_result

        # 권고 ④ — backoff 재시도
        for attempt in range(MAX_ATTEMPTS):
            self.server_calls += 1
            r = await self._client.post(
                "/shorten",
                json={"url": url},
                headers={**self._headers, "content-type": "application/json"},
            )

            if r.status_code == 200:
                body = r.json()
                result = ShortenResult(
                    code=body["code"],
                    limit=int(r.headers.get("x-ratelimit-limit", 0)),
                    remaining=int(r.headers.get("x-ratelimit-remaining", 0)),
                )
                # 권고 ① — 캐시 저장
                self._cache[url] = (result, time.time() + CACHE_TTL_S)
                return result

            if r.status_code == 429:
                if attempt == MAX_ATTEMPTS - 1:
                    return RateLimitedResult(
                        retry_after=float(r.headers.get("x-ratelimit-retry-after", 0)),
                        limit=int(r.headers.get("x-ratelimit-limit", 0)),
                    )
                # Retry-After 우선, 없으면 지수
                retry_after = float(r.headers.get("x-ratelimit-retry-after", 0))
                if retry_after > 0:
                    wait = min(retry_after, MAX_BACKOFF_S)
                else:
                    wait = min(BASE_BACKOFF_S * (2 ** attempt), MAX_BACKOFF_S)
                self.backoff_waits += 1
                await asyncio.sleep(wait)
                continue

            # 다른 status code (5xx 등)
            r.raise_for_status()

        # 도달 못 함
        raise RuntimeError("unreachable")

    async def aclose(self) -> None:
        await self._client.aclose()
