from app.limiter.always_allow import AlwaysAllow
from app.limiter.base import Limiter
from app.limiter.fixed_window import FixedWindow
from app.limiter.token_bucket import TokenBucket

_LIMITERS: dict[str, Limiter] = {
    "always_allow": AlwaysAllow(),
    "token_bucket": TokenBucket(),
    "fixed_window": FixedWindow(),
}


def get_limiter(algorithm: str) -> Limiter:
    try:
        return _LIMITERS[algorithm]
    except KeyError as e:
        raise KeyError(f"unknown algorithm: {algorithm}") from e
