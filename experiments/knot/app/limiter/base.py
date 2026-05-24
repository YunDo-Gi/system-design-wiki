# experiments/knot/app/limiter/base.py
from __future__ import annotations

from typing import NamedTuple, Protocol


class Rule(NamedTuple):
    algorithm: str
    unit: str                      # "second" | "minute" | "hour"
    requests_per_unit: int
    burst: int | None = None       # token bucket용


class Decision(NamedTuple):
    allowed: bool
    limit: int
    remaining: int
    retry_after: float             # allowed=True이면 0.0


class Limiter(Protocol):
    async def allow(self, key: str, rule: Rule) -> Decision: ...
