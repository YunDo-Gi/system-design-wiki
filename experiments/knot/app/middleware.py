from __future__ import annotations

import asyncio
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.limiter import registry as limiter_registry
from app.limiter.base import Decision, Rule

logger = logging.getLogger(__name__)

MAX_THROTTLE_MS = 2000  # soft mode가 이 이상 throttle해야 하면 hard 폴백


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        rules = getattr(request.app.state, "rules", None)

        endpoint = self._endpoint_name(request)
        user_tier = request.headers.get("x-user-tier", "default")
        rule = (
            rules.lookup([("endpoint", endpoint), ("user_tier", user_tier)])
            if rules and endpoint
            else None
        )

        if rule is None:
            logger.info("no rule for endpoint=%s — passing through", endpoint)
            return await call_next(request)

        identity = request.headers.get("x-api-key") or (
            request.client.host if request.client else "unknown"
        )
        key = f"knot:{endpoint}:{identity}"

        limiter = limiter_registry.get_limiter(rule.algorithm)
        decision = await limiter.allow(key, rule)

        if decision.allowed:
            response = await call_next(request)
            response.headers["X-Ratelimit-Limit"] = str(decision.limit)
            response.headers["X-Ratelimit-Remaining"] = str(decision.remaining)
            return response

        # Denied — mode 분기
        if rule.mode == "soft":
            throttle_ms = int(decision.retry_after * 1000)
            if throttle_ms < MAX_THROTTLE_MS:
                await asyncio.sleep(throttle_ms / 1000)
                response = await call_next(request)
                response.headers["X-Ratelimit-Limit"] = str(decision.limit)
                response.headers["X-Ratelimit-Remaining"] = "0"
                response.headers["X-Ratelimit-Throttled"] = "true"
                response.headers["X-Ratelimit-Throttle-Ms"] = str(throttle_ms)
                return response
            # throttle 너무 길면 hard 폴백
            logger.info("soft throttle would exceed cap (%dms) — falling back to hard", throttle_ms)

        # hard (default 또는 soft fallback)
        return self._deny_response(decision)

    @staticmethod
    def _deny_response(decision: Decision) -> Response:
        return Response(
            status_code=429,
            headers={
                "X-Ratelimit-Limit": str(decision.limit),
                "X-Ratelimit-Remaining": str(decision.remaining),
                "X-Ratelimit-Retry-After": f"{decision.retry_after:.3f}",
            },
        )

    @staticmethod
    def _endpoint_name(request: Request) -> str | None:
        path = request.url.path
        if path == "/shorten":
            return "shorten"
        if path == "/healthz":
            return None
        if path.startswith("/") and "/" not in path[1:] and path != "/":
            return "redirect"
        return None
