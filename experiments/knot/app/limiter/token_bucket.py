from __future__ import annotations

from pathlib import Path

from app.limiter.base import Decision, Rule
from app.redis_client import get_redis

_SCRIPT_PATH = Path(__file__).parent / "scripts" / "token_bucket.lua"
_SCRIPT_SRC = _SCRIPT_PATH.read_text()

_UNIT_SECONDS = {"second": 1, "minute": 60, "hour": 3600}


class TokenBucket:
    def __init__(self) -> None:
        self._script_src = _SCRIPT_SRC
        self._script = None  # lazy register on first allow()

    async def allow(self, key: str, rule: Rule) -> Decision:
        if self._script is None:
            self._script = get_redis().register_script(self._script_src)

        capacity = rule.burst or rule.requests_per_unit
        rate = rule.requests_per_unit / _UNIT_SECONDS[rule.unit]
        bucket_key = key.replace("knot:", "knot:bucket:", 1)

        result = await self._script(keys=[bucket_key], args=[capacity, rate, 1])
        allowed, remaining, retry_ms = result

        return Decision(
            allowed=bool(int(allowed)),
            limit=capacity,
            remaining=int(remaining),
            retry_after=int(retry_ms) / 1000.0,
        )
