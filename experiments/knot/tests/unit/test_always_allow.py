# experiments/knot/tests/unit/test_always_allow.py
import pytest

from app.limiter.always_allow import AlwaysAllow
from app.limiter.base import Rule


@pytest.mark.asyncio
async def test_always_allow_returns_allowed_true():
    limiter = AlwaysAllow()
    rule = Rule(algorithm="always_allow", unit="second", requests_per_unit=10)
    decision = await limiter.allow("any-key", rule)
    assert decision.allowed is True
    assert decision.limit == 10
    assert decision.remaining == 10
    assert decision.retry_after == 0.0


@pytest.mark.asyncio
async def test_always_allow_ignores_key_and_state():
    limiter = AlwaysAllow()
    rule = Rule(algorithm="always_allow", unit="second", requests_per_unit=5)
    for _ in range(100):
        decision = await limiter.allow("same-key", rule)
        assert decision.allowed is True
