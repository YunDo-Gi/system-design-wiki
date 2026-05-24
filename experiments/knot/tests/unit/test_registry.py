import pytest

from app.limiter.always_allow import AlwaysAllow
from app.limiter.registry import get_limiter


def test_registry_returns_always_allow():
    limiter = get_limiter("always_allow")
    assert isinstance(limiter, AlwaysAllow)


def test_registry_unknown_algorithm_raises():
    with pytest.raises(KeyError, match="unknown algorithm"):
        get_limiter("not_a_real_algo")
