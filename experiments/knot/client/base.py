from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ShortenResult:
    code: str
    limit: int                          # X-Ratelimit-Limit
    remaining: int                      # X-Ratelimit-Remaining
    cached: bool = False                # SDK 내부 캐시 히트 여부


@dataclass
class RateLimitedResult:
    retry_after: float                  # 초
    limit: int
    raw_status: int = 429
