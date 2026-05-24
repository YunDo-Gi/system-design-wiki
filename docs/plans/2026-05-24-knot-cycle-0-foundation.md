# knot Cycle 0 — Foundation 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `experiments/knot/`에 FastAPI 앱·미들웨어 셸·규칙 로더·`AlwaysAllow` 더미 limiter·Redis docker-compose·테스트 골격을 만들어, 이후 사이클이 알고리즘 모듈만 추가하면 동작하는 베이스를 완성한다.

**Architecture:** FastAPI + Starlette middleware. `Limiter` Protocol을 plug-in 포인트로 두고 사이클 0에서는 `AlwaysAllow` 1개만 등록한다. 규칙은 `rules.yaml` (Lyft envoy 포맷)에서 시작 시 로드. Redis는 docker-compose로 띄워두고 `/healthz`로 연결만 검증(실제 카운터는 사이클 1+에서 사용).

**Tech Stack:** Python 3.12, FastAPI, uvicorn, redis-py(async), PyYAML, pytest, pytest-asyncio, httpx, fakeredis. 패키지 매니저는 `uv` (lockfile 빠르고 가상환경 일관). Docker로 Redis.

**Spec 참조:** `docs/specs/2026-05-24-rate-limiter-design.md` §2-2, §3, §4, §7 cycle 0.

---

## File Structure

```
experiments/knot/
  pyproject.toml              # uv project, 의존성
  docker-compose.yml          # redis 서비스
  rules.yaml                  # Lyft envoy 포맷 — 사이클 0은 always_allow만
  README.md                   # 빠른 시작 + ch08 진화 노트 + Obsidian excluded 안내
  .python-version
  app/
    __init__.py
    main.py                   # FastAPI 앱, mock 핸들러, 미들웨어 마운트, /healthz
    middleware.py             # RateLimitMiddleware (Starlette BaseHTTPMiddleware)
    rules.py                  # YAML 로더 + lookup
    redis_client.py           # 싱글톤 async Redis 클라이언트 (이후 사이클 활용)
    limiter/
      __init__.py
      base.py                 # Rule, Decision, Limiter Protocol
      registry.py             # 알고리즘 이름 → Limiter 인스턴스
      always_allow.py         # 더미 limiter
  tests/
    __init__.py
    conftest.py               # TestClient/AsyncClient fixture
    unit/
      __init__.py
      test_rules.py
      test_always_allow.py
    integration/
      __init__.py
      test_middleware_e2e.py
      test_healthz.py
```

**책임 분담**
- `limiter/base.py` — 타입과 인터페이스만. 어떤 구현체도 import 하지 않는다.
- `limiter/registry.py` — 알고리즘 이름 → `Limiter` 인스턴스 매핑. 새 알고리즘 추가는 이 파일 1줄만 수정.
- `middleware.py` — 식별·규칙 조회·limiter 호출·헤더 주입·429 분기.
- `rules.py` — YAML I/O + lookup. 핫리로드는 사이클 6.
- `main.py` — 앱 부팅·라우트·미들웨어 등록.

---

## Task 1: 프로젝트 스캐폴딩

**Files:**
- Create: `experiments/knot/pyproject.toml`
- Create: `experiments/knot/.python-version`
- Create: `experiments/knot/docker-compose.yml`
- Create: `experiments/knot/README.md`
- Create: `experiments/knot/app/__init__.py` (빈 파일)
- Create: `experiments/knot/app/limiter/__init__.py` (빈 파일)
- Create: `experiments/knot/tests/__init__.py` (빈 파일)
- Create: `experiments/knot/tests/unit/__init__.py` (빈 파일)
- Create: `experiments/knot/tests/integration/__init__.py` (빈 파일)

- [ ] **Step 1: 디렉터리 생성**

```bash
mkdir -p experiments/knot/app/limiter
mkdir -p experiments/knot/tests/unit
mkdir -p experiments/knot/tests/integration
touch experiments/knot/app/__init__.py
touch experiments/knot/app/limiter/__init__.py
touch experiments/knot/tests/__init__.py
touch experiments/knot/tests/unit/__init__.py
touch experiments/knot/tests/integration/__init__.py
```

- [ ] **Step 2: `.python-version`**

```
3.12
```

- [ ] **Step 3: `pyproject.toml`**

```toml
[project]
name = "knot"
version = "0.0.0"
description = "URL shortener mock for ch04 rate limiter learning experiments"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "redis>=5.0",
    "pyyaml>=6.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
    "fakeredis>=2.21",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 4: `docker-compose.yml`**

```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 2s
      timeout: 1s
      retries: 5
```

- [ ] **Step 5: 최소 `README.md`** (이후 Task 9에서 보강)

```markdown
# knot — URL shortener mock for ch04 rate limiter experiments

학습용 프로젝트. 자세한 설계는 `../../docs/specs/2026-05-24-rate-limiter-design.md`.

## 빠른 시작 (사이클 0)

\`\`\`bash
cd experiments/knot
docker compose up -d redis
uv sync
uv run uvicorn app.main:app --reload
\`\`\`

## Obsidian 사용자

Settings → Files & Links → **Excluded files**에 `experiments/`를 추가하세요. vault 인덱싱 부하 및 탐색기 오염을 막습니다.
```

- [ ] **Step 6: `uv sync`로 환경 생성**

Run:
```bash
cd experiments/knot && uv sync
```
Expected: `.venv/` 생성, `uv.lock` 생성. 에러 없음.

- [ ] **Step 7: 커밋**

```bash
git add experiments/knot
git commit -m "experiment: knot cycle 0 scaffolding (pyproject, docker-compose, dirs)"
```

---

## Task 2: Limiter 타입 정의 (Rule, Decision, Protocol)

**Files:**
- Create: `experiments/knot/app/limiter/base.py`

- [ ] **Step 1: `base.py` 작성**

```python
# experiments/knot/app/limiter/base.py
from __future__ import annotations

from typing import NamedTuple, Protocol


class Rule(NamedTuple):
    algorithm: str
    unit: str                      # "second" | "minute" | "hour"
    requests_per_unit: int
    burst: int | None = None       # token bucket용
    mode: str = "hard"             # "hard" | "soft"


class Decision(NamedTuple):
    allowed: bool
    limit: int
    remaining: int
    retry_after: float             # allowed=True이면 0.0


class Limiter(Protocol):
    async def allow(self, key: str, rule: Rule) -> Decision: ...
```

- [ ] **Step 2: 구문 검증**

Run:
```bash
cd experiments/knot && uv run python -c "from app.limiter.base import Rule, Decision, Limiter; print(Rule.__annotations__)"
```
Expected: `{'algorithm': <class 'str'>, ...}` 출력, 에러 없음.

- [ ] **Step 3: 커밋**

```bash
git add experiments/knot/app/limiter/base.py
git commit -m "experiment: knot Rule/Decision/Limiter Protocol 타입 정의"
```

---

## Task 3: AlwaysAllow limiter (TDD)

**Files:**
- Test: `experiments/knot/tests/unit/test_always_allow.py`
- Create: `experiments/knot/app/limiter/always_allow.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run:
```bash
cd experiments/knot && uv run pytest tests/unit/test_always_allow.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.limiter.always_allow'`

- [ ] **Step 3: 최소 구현**

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run:
```bash
cd experiments/knot && uv run pytest tests/unit/test_always_allow.py -v
```
Expected: 2 passed.

- [ ] **Step 5: 커밋**

```bash
git add experiments/knot/app/limiter/always_allow.py experiments/knot/tests/unit/test_always_allow.py
git commit -m "experiment: knot AlwaysAllow limiter + unit tests"
```

---

## Task 4: Limiter Registry

**Files:**
- Create: `experiments/knot/app/limiter/registry.py`
- Test: `experiments/knot/tests/unit/test_registry.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# experiments/knot/tests/unit/test_registry.py
import pytest

from app.limiter.always_allow import AlwaysAllow
from app.limiter.registry import get_limiter


def test_registry_returns_always_allow():
    limiter = get_limiter("always_allow")
    assert isinstance(limiter, AlwaysAllow)


def test_registry_unknown_algorithm_raises():
    with pytest.raises(KeyError, match="unknown algorithm"):
        get_limiter("not_a_real_algo")
```

- [ ] **Step 2: 테스트 실패 확인**

Run:
```bash
cd experiments/knot && uv run pytest tests/unit/test_registry.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.limiter.registry'`

- [ ] **Step 3: 최소 구현**

```python
# experiments/knot/app/limiter/registry.py
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run:
```bash
cd experiments/knot && uv run pytest tests/unit/test_registry.py -v
```
Expected: 2 passed.

- [ ] **Step 5: 커밋**

```bash
git add experiments/knot/app/limiter/registry.py experiments/knot/tests/unit/test_registry.py
git commit -m "experiment: knot limiter registry (always_allow only for cycle 0)"
```

---

## Task 5: Rules 로더 (TDD)

**Files:**
- Test: `experiments/knot/tests/unit/test_rules.py`
- Create: `experiments/knot/app/rules.py`
- Create: `experiments/knot/rules.yaml`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# experiments/knot/tests/unit/test_rules.py
import textwrap

import pytest

from app.limiter.base import Rule
from app.rules import Rules, load_rules


def test_load_rules_parses_descriptors(tmp_path):
    yaml_text = textwrap.dedent("""
        domain: knot
        descriptors:
          - key: endpoint
            value: shorten
            rate_limit:
              algorithm: always_allow
              unit: minute
              requests_per_unit: 10
          - key: endpoint
            value: redirect
            rate_limit:
              algorithm: always_allow
              unit: second
              requests_per_unit: 50
              burst: 100
              mode: soft
    """)
    yaml_file = tmp_path / "rules.yaml"
    yaml_file.write_text(yaml_text)

    rules = load_rules(yaml_file)

    assert rules.domain == "knot"
    shorten = rules.lookup("endpoint", "shorten")
    assert shorten == Rule(algorithm="always_allow", unit="minute", requests_per_unit=10)
    redirect = rules.lookup("endpoint", "redirect")
    assert redirect == Rule(
        algorithm="always_allow",
        unit="second",
        requests_per_unit=50,
        burst=100,
        mode="soft",
    )


def test_lookup_missing_returns_none(tmp_path):
    yaml_file = tmp_path / "rules.yaml"
    yaml_file.write_text("domain: knot\ndescriptors: []\n")
    rules = load_rules(yaml_file)
    assert rules.lookup("endpoint", "nonexistent") is None
```

- [ ] **Step 2: 테스트 실패 확인**

Run:
```bash
cd experiments/knot && uv run pytest tests/unit/test_rules.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.rules'`

- [ ] **Step 3: 최소 구현**

```python
# experiments/knot/app/rules.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.limiter.base import Rule


@dataclass
class Rules:
    domain: str
    _index: dict[tuple[str, str], Rule] = field(default_factory=dict)

    def lookup(self, key: str, value: str) -> Rule | None:
        return self._index.get((key, value))


def load_rules(path: Path) -> Rules:
    data = yaml.safe_load(Path(path).read_text())
    rules = Rules(domain=data["domain"])
    for d in data.get("descriptors") or []:
        rl = d["rate_limit"]
        rule = Rule(
            algorithm=rl["algorithm"],
            unit=rl["unit"],
            requests_per_unit=rl["requests_per_unit"],
            burst=rl.get("burst"),
            mode=rl.get("mode", "hard"),
        )
        rules._index[(d["key"], d["value"])] = rule
    return rules
```

- [ ] **Step 4: 테스트 통과 확인**

Run:
```bash
cd experiments/knot && uv run pytest tests/unit/test_rules.py -v
```
Expected: 2 passed.

- [ ] **Step 5: 실제 `rules.yaml` 작성** (사이클 0은 모두 always_allow)

```yaml
# experiments/knot/rules.yaml
domain: knot
descriptors:
  - key: endpoint
    value: shorten
    rate_limit:
      algorithm: always_allow
      unit: minute
      requests_per_unit: 10
  - key: endpoint
    value: redirect
    rate_limit:
      algorithm: always_allow
      unit: second
      requests_per_unit: 50
```

- [ ] **Step 6: 커밋**

```bash
git add experiments/knot/app/rules.py experiments/knot/tests/unit/test_rules.py experiments/knot/rules.yaml
git commit -m "experiment: knot rules.yaml 로더 + lookup + unit tests"
```

---

## Task 6: Redis 클라이언트 싱글톤

**Files:**
- Create: `experiments/knot/app/redis_client.py`

- [ ] **Step 1: 작성**

```python
# experiments/knot/app/redis_client.py
from __future__ import annotations

import os

from redis.asyncio import Redis

_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        _client = Redis.from_url(url, decode_responses=True)
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
```

- [ ] **Step 2: 모듈 import 검증**

Run:
```bash
cd experiments/knot && uv run python -c "from app.redis_client import get_redis; print(get_redis())"
```
Expected: `Redis<ConnectionPool<...>>` 같은 출력, 에러 없음 (실제 연결은 안 함).

- [ ] **Step 3: 커밋**

```bash
git add experiments/knot/app/redis_client.py
git commit -m "experiment: knot async Redis 싱글톤 (사이클 1+에서 활용)"
```

---

## Task 7: FastAPI 앱 + mock 핸들러 + /healthz

**Files:**
- Create: `experiments/knot/app/main.py`

- [ ] **Step 1: 작성**

```python
# experiments/knot/app/main.py
from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.middleware import RateLimitMiddleware
from app.redis_client import close_redis, get_redis
from app.rules import Rules, load_rules

RULES_PATH = Path(__file__).parent.parent / "rules.yaml"

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
```

- [ ] **Step 2: 앱 import 검증**

Run:
```bash
cd experiments/knot && uv run python -c "from app.main import app; print([r.name for r in app.routes if r.name])"
```
Expected: `['healthz', 'shorten', 'redirect']` 포함.

- [ ] **Step 3: 커밋**

```bash
git add experiments/knot/app/main.py
git commit -m "experiment: knot FastAPI 앱 + mock /shorten /{code} + /healthz"
```

---

## Task 8: RateLimit Middleware (TDD)

**Files:**
- Test: `experiments/knot/tests/integration/test_middleware_e2e.py`
- Test: `experiments/knot/tests/conftest.py`
- Create: `experiments/knot/app/middleware.py`

- [ ] **Step 1: conftest fixture**

```python
# experiments/knot/tests/conftest.py
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client():
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
```

- [ ] **Step 2: 실패하는 테스트 작성**

```python
# experiments/knot/tests/integration/test_middleware_e2e.py
import pytest


@pytest.mark.asyncio
async def test_shorten_returns_200_with_rate_limit_headers(client):
    response = await client.post("/shorten", json={"url": "https://example.com"})
    assert response.status_code == 200
    assert response.headers["x-ratelimit-limit"] == "10"
    assert response.headers["x-ratelimit-remaining"] == "10"
    assert "x-ratelimit-retry-after" not in response.headers


@pytest.mark.asyncio
async def test_redirect_returns_302_with_rate_limit_headers(client):
    create = await client.post("/shorten", json={"url": "https://example.com"})
    code = create.json()["code"]
    response = await client.get(f"/{code}", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["x-ratelimit-limit"] == "50"


@pytest.mark.asyncio
async def test_unknown_endpoint_still_passes(client):
    response = await client.get("/healthz")
    assert response.status_code == 200
```

- [ ] **Step 3: 테스트 실패 확인**

Run:
```bash
cd experiments/knot && uv run pytest tests/integration/test_middleware_e2e.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.middleware'`

- [ ] **Step 4: 미들웨어 구현**

```python
# experiments/knot/app/middleware.py
from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.limiter.registry import get_limiter

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        rules = getattr(request.app.state, "rules", None)

        endpoint = self._endpoint_name(request)
        rule = rules.lookup("endpoint", endpoint) if rules and endpoint else None

        if rule is None:
            logger.info("no rule for endpoint=%s — passing through", endpoint)
            return await call_next(request)

        identity = request.headers.get("x-api-key") or (request.client.host if request.client else "unknown")
        key = f"knot:{endpoint}:{identity}"

        limiter = get_limiter(rule.algorithm)
        decision = await limiter.allow(key, rule)

        if not decision.allowed:
            headers = {
                "X-Ratelimit-Limit": str(decision.limit),
                "X-Ratelimit-Remaining": str(decision.remaining),
                "X-Ratelimit-Retry-After": f"{decision.retry_after:.3f}",
            }
            return Response(status_code=429, headers=headers)

        response = await call_next(request)
        response.headers["X-Ratelimit-Limit"] = str(decision.limit)
        response.headers["X-Ratelimit-Remaining"] = str(decision.remaining)
        return response

    @staticmethod
    def _endpoint_name(request: Request) -> str | None:
        route = request.scope.get("route")
        return getattr(route, "name", None) if route else None
```

**중요**: Starlette는 미들웨어 진입 시점엔 라우트가 아직 매칭되지 않아 `request.scope["route"]`가 없을 수 있다. 우리는 path-based fallback이 필요하다. 다음 스텝에서 테스트가 어떻게 나오는지 보고 결정.

- [ ] **Step 5: 첫 실행 — 라우트 매칭 시점 검증**

Run:
```bash
cd experiments/knot && uv run pytest tests/integration/test_middleware_e2e.py -v
```
Expected 두 가지 중 하나:
- (A) 통과 — Starlette가 매칭 후 미들웨어를 호출하는 케이스 (`BaseHTTPMiddleware`는 사실 dispatch 시점에 route 결정됨)
- (B) `endpoint`가 None이라 `no rule` 로그 → 헤더 누락으로 실패

(B)인 경우 Step 6으로, (A)인 경우 Step 7로.

- [ ] **Step 6: (필요 시) path-based fallback**

`_endpoint_name`을 path로 결정하도록 교체:

```python
    @staticmethod
    def _endpoint_name(request: Request) -> str | None:
        path = request.url.path
        if path == "/shorten":
            return "shorten"
        if path == "/healthz":
            return None  # 규칙 없음 → 통과
        # /{code} 패턴: 슬래시 1개로 시작하고 슬래시 더 없음
        if path.startswith("/") and "/" not in path[1:] and path != "/":
            return "redirect"
        return None
```

Run:
```bash
cd experiments/knot && uv run pytest tests/integration/test_middleware_e2e.py -v
```
Expected: 3 passed.

- [ ] **Step 7: 커밋**

```bash
git add experiments/knot/app/middleware.py experiments/knot/tests/conftest.py experiments/knot/tests/integration/test_middleware_e2e.py
git commit -m "experiment: knot RateLimit middleware + e2e tests"
```

---

## Task 9: /healthz integration 테스트 (실제 Redis)

**Files:**
- Test: `experiments/knot/tests/integration/test_healthz.py`

- [ ] **Step 1: 테스트 작성**

```python
# experiments/knot/tests/integration/test_healthz.py
import os

import pytest


@pytest.mark.asyncio
async def test_healthz_reports_redis_ok_when_available(client):
    response = await client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    if os.environ.get("REDIS_AVAILABLE") == "1":
        assert body["redis"] == "ok"
    else:
        assert body["redis"].startswith(("ok", "error"))
```

- [ ] **Step 2: Redis 띄우고 실행**

Run:
```bash
cd experiments/knot && docker compose up -d redis
REDIS_AVAILABLE=1 uv run pytest tests/integration/test_healthz.py -v
```
Expected: 1 passed, body에 `redis: ok`.

- [ ] **Step 3: 전체 테스트 실행**

Run:
```bash
cd experiments/knot && REDIS_AVAILABLE=1 uv run pytest -v
```
Expected: 모든 테스트 통과 (unit + integration).

- [ ] **Step 4: 커밋**

```bash
git add experiments/knot/tests/integration/test_healthz.py
git commit -m "experiment: knot /healthz Redis 연결 검증 테스트"
```

---

## Task 10: README 보강 + spec status 업데이트 + log.md

**Files:**
- Modify: `experiments/knot/README.md`
- Modify: `docs/specs/2026-05-24-rate-limiter-design.md` (§7 cycle 0 status)
- Modify: `log.md`

- [ ] **Step 1: README 보강**

`experiments/knot/README.md`를 다음 내용으로 교체:

```markdown
# knot — URL shortener mock for ch04 rate limiter experiments

학습용 프로젝트. ch04에 등장하는 모든 핵심 개념과 추가 토픽을 직접 구현·검증한다.
자세한 설계는 `../../docs/specs/2026-05-24-rate-limiter-design.md`.

## 빠른 시작

```bash
cd experiments/knot
docker compose up -d redis
uv sync
uv run uvicorn app.main:app --reload
```

별도 터미널에서:
```bash
curl -X POST localhost:8000/shorten \
  -H "content-type: application/json" \
  -H "x-api-key: my-key" \
  -d '{"url": "https://example.com"}'
# {"code": "abc123"}

curl -i localhost:8000/abc123
# HTTP/1.1 302
# X-Ratelimit-Limit: 50
# X-Ratelimit-Remaining: 50
# Location: https://example.com
```

## 테스트

```bash
docker compose up -d redis
REDIS_AVAILABLE=1 uv run pytest -v
```

## 디렉터리

- `app/` — FastAPI 앱, 미들웨어, 규칙 로더, limiter plug-in
- `app/limiter/` — 알고리즘 모듈 (cycle 0: always_allow만)
- `rules.yaml` — Lyft envoy 포맷 규칙
- `tests/unit/`, `tests/integration/`
- `load/` — k6 시나리오 (cycle 1+에서 추가)
- `reports/` — 부하 시험 리포트 (cycle 1+에서 추가)

## Obsidian 사용자

Settings → Files & Links → **Excluded files**에 `experiments/`를 추가하세요.
`.venv/`·`__pycache__/` 등이 vault에 노출되어 인덱싱이 느려지는 것을 막습니다.

## 향후 진화 (ch05~08)

본 사이클은 `POST /shorten`과 `GET /{code}`를 한 앱 안의 mock으로 두지만,
실서비스에서는 두 경로의 부하 특성이 정반대라 거의 항상 분리한다:

| | `POST /shorten` | `GET /{code}` |
|---|---|---|
| QPS | 낮음 | 압도적으로 높음 (클릭마다 1회) |
| 지연 민감도 | 보통 | 극도로 민감 |
| 저장소 | primary DB | read replica / KV / edge cache |
| 배포 | 중앙 | edge 가까이, 다지역 |
| rate limit | API 키 단위 쿼터 | IP·지역 단위 abuse 방어 |

이 분리는 ch05(consistent hashing) · ch06(KV store) · ch07(unique ID) · **ch08(URL Shortener)** 에서 다룬다.
본 사이클은 미들웨어가 엔드포인트별로 다른 규칙·다른 알고리즘을 적용할 수 있게 설계해 ch08 시점에 양쪽 서비스로 이식 가능하게 했다.
```

- [ ] **Step 2: spec status 업데이트**

`docs/specs/2026-05-24-rate-limiter-design.md`의 §7 사이클 로드맵 표에서:

old:
```
| 0 | Foundation — ... | API gateway 위치, 응답 헤더 표준 | todo |
```

new:
```
| 0 | Foundation — ... | API gateway 위치, 응답 헤더 표준 | done (2026-05-24) |
```

- [ ] **Step 3: log.md append**

`log.md` 끝에 다음을 추가:

```markdown

## [2026-05-24] experiment | knot cycle 0: Foundation

FastAPI 앱·미들웨어 셸·규칙 로더·AlwaysAllow dummy limiter·Redis docker-compose·테스트 골격 완성. 사이클 1(token bucket)부터는 limiter 모듈 추가만으로 동작.

- `experiments/knot/` 전체 신규
- 사이클 1+에서 같은 인터페이스로 5개 알고리즘 확장
```

- [ ] **Step 4: stub 점검 + 최종 커밋**

Run:
```bash
git status --short
# wiki/ 외부에 의도하지 않은 빈 .md 있는지 확인
find . -maxdepth 3 -name "*.md" -size 0 -not -path "./.git/*"
```
Expected: 빈 .md 없음. `experiments/knot/README.md`와 spec, log.md만 변경됨.

```bash
git add experiments/knot/README.md docs/specs/2026-05-24-rate-limiter-design.md log.md
git commit -m "experiment: knot cycle 0 완료 — README 보강 + spec status + log"
git push
```

Expected: push 성공.

---

## 검증 체크리스트 (사이클 0 완료 기준)

- [ ] `uv run pytest -v` 전체 통과 (unit 5개 + integration 4개 = 9개)
- [ ] `docker compose up -d redis && curl localhost:8000/healthz` → `{"status": "ok", "redis": "ok"}`
- [ ] `curl -X POST localhost:8000/shorten -d '{"url": "https://example.com"}' -H "content-type: application/json"` → 200, `X-Ratelimit-*` 헤더 포함
- [ ] `curl -i localhost:8000/<code>` → 302, `X-Ratelimit-*` 헤더 포함
- [ ] 모든 commit이 `experiment:` prefix (Task 10 spec/log 갱신은 같은 commit에 묶임)
- [ ] spec §7 cycle 0 status = `done (2026-05-24)`
- [ ] log.md에 cycle 0 항목 추가
- [ ] push 완료

## 다음 사이클

**Cycle 1 — Token Bucket**:
- `app/limiter/token_bucket.py` (Redis Lua script로 atomic refill+take)
- `app/limiter/registry.py`에 1줄 추가
- `rules.yaml`의 `redirect` 규칙을 `algorithm: token_bucket`로 변경 (`burst: 100`)
- `tests/unit/test_token_bucket.py` (fakeredis + frozen time)
- `tests/integration/test_token_bucket_redis.py` (실제 Redis)
- `load/token_bucket.k6.js` (burst 시나리오)
- `scripts/report.py` (k6 JSON → matplotlib → md) — 처음이라 이 사이클에서 작성
- `reports/token_bucket.md`
- 위키 [[token-bucket-algorithm]] "등장 사례"에 cross-link 추가
- spec §7 status `done` 갱신 + log.md append

Cycle 1 plan은 cycle 0 완료 후 별도 파일(`docs/plans/YYYY-MM-DD-knot-cycle-1-token-bucket.md`)로 작성한다.
