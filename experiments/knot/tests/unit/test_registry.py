import pytest

from app.limiter.registry import get_limiter
from app.limiter.token_bucket import TokenBucket


def test_registry_returns_token_bucket():
    limiter = get_limiter("token_bucket")
    assert isinstance(limiter, TokenBucket)


def test_registry_unknown_algorithm_raises():
    with pytest.raises(KeyError, match="unknown algorithm"):
        get_limiter("not_a_real_algo")
