from __future__ import annotations

from pathlib import Path

from app.limiter.base import Decision, Rule
from app.redis_client import get_redis

_SCRIPT_PATH = Path(__file__).parent / "scripts" / "fixed_window.lua"
_SCRIPT_SRC = _SCRIPT_PATH.read_text()

_UNIT_SECONDS = {"second": 1, "minute": 60, "hour": 3600}


class FixedWindow:
    def __init__(self) -> None:
        self._script = None
        self._script_client = None

    async def allow(self, key: str, rule: Rule) -> Decision:
        client = get_redis()
        if self._script is None or self._script_client is not client:
            self._script = client.register_script(_SCRIPT_SRC)
            self._script_client = client

        window_size = _UNIT_SECONDS[rule.unit]
        base_key = key.replace("knot:", "knot:fw:", 1)

        result = await self._script(
            keys=[base_key],
            args=[rule.requests_per_unit, window_size],
        )
        allowed, limit, remaining, retry_ms, _window_start = result

        return Decision(
            allowed=bool(int(allowed)),
            limit=int(limit),
            remaining=int(remaining),
            retry_after=int(retry_ms) / 1000.0,
        )
