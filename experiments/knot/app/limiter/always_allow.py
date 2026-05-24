# experiments/knot/app/limiter/always_allow.py
from app.limiter.base import Decision, Rule


class AlwaysAllow:
    async def allow(self, key: str, rule: Rule) -> Decision:
        return Decision(
            allowed=True,
            limit=rule.requests_per_unit,
            remaining=rule.requests_per_unit,
            retry_after=0.0,
        )
