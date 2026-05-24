# experiments/knot/app/limiter/sliding_window_log.py
from __future__ import annotations

import secrets
from pathlib import Path

from app.limiter.base import Decision, Rule
from app.redis_client import get_redis

_SCRIPT_PATH = Path(__file__).parent / "scripts" / "sliding_window_log.lua"
_SCRIPT_SRC = _SCRIPT_PATH.read_text()

_UNIT_SECONDS = {"second": 1, "minute": 60, "hour": 3600}


class SlidingWindowLog:
    def __init__(self) -> None:
        self._script = None
        self._script_client = None

    async def allow(self, key: str, rule: Rule) -> Decision:
        client = get_redis()
        if self._script is None or self._script_client is not client:
            self._script = client.register_script(_SCRIPT_SRC)
            self._script_client = client

        window_size = _UNIT_SECONDS[rule.unit]
        zset_key = key.replace("knot:", "knot:swl:", 1)
        random_hex = secrets.token_hex(2)  # 4 hex chars

        result = await self._script(
            keys=[zset_key],
            args=[rule.requests_per_unit, window_size, random_hex],
        )
        allowed, limit, remaining, retry_ms = result

        return Decision(
            allowed=bool(int(allowed)),
            limit=int(limit),
            remaining=int(remaining),
            retry_after=int(retry_ms) / 1000.0,
        )
