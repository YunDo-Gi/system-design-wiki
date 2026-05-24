from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.middleware import RateLimitMiddleware
from app.redis_client import close_redis, get_redis
from app.rules import Rules, load_rules

RULES_PATH = Path(os.environ.get("KNOT_RULES_PATH", str(Path(__file__).parent.parent / "rules.yaml")))

# in-memory mock store: code -> url
_store: dict[str, str] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.rules = load_rules(RULES_PATH)
    yield
    await close_redis()


app = FastAPI(lifespan=lifespan)
app.add_middleware(RateLimitMiddleware)


@app.get("/healthz")
async def healthz():
    try:
        pong = await get_redis().ping()
        return {"status": "ok", "redis": "ok" if pong else "fail"}
    except Exception as e:
        return {"status": "degraded", "redis": f"error: {e}"}


@app.post("/shorten", name="shorten")
async def shorten(payload: dict, request: Request):
    url = payload.get("url")
    if not isinstance(url, str) or not url:
        raise HTTPException(status_code=400, detail="url required")
    code = secrets.token_urlsafe(6)
    _store[code] = url
    return {"code": code}


@app.get("/{code}", name="redirect")
async def redirect(code: str):
    url = _store.get(code)
    if url is None:
        raise HTTPException(status_code=404, detail="not found")
    return RedirectResponse(url=url, status_code=302)
