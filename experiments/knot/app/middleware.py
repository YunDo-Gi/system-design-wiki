from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Placeholder. Real implementation lands in Task 8."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
