from app.limiter.base import Limiter
from app.limiter.token_bucket import TokenBucket

_LIMITERS: dict[str, Limiter] = {
    "token_bucket": TokenBucket(),
}


def get_limiter(algorithm: str) -> Limiter:
    try:
        return _LIMITERS[algorithm]
    except KeyError as e:
        raise KeyError(f"unknown algorithm: {algorithm}") from e
