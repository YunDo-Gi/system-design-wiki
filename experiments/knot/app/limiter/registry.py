from app.limiter.always_allow import AlwaysAllow
from app.limiter.base import Limiter

_LIMITERS: dict[str, Limiter] = {
    "always_allow": AlwaysAllow(),
}


def get_limiter(algorithm: str) -> Limiter:
    try:
        return _LIMITERS[algorithm]
    except KeyError as e:
        raise KeyError(f"unknown algorithm: {algorithm}") from e
