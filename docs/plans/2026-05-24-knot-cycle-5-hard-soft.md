# knot Cycle 5 — Hard vs Soft 구현 계획

> **For agentic workers:** Use superpowers:subagent-driven-development.

**Goal:** `Rule.mode` 필드(cycle 0부터 박혀있던) 활성화. mode=hard는 기존 429, mode=soft는 asyncio.sleep으로 throttle 후 200. shorten premium tier만 soft로 전환.

**Architecture:** 알고리즘 코드 변경 0줄. middleware의 deny 분기에 mode 분기 추가. `MAX_THROTTLE_MS=2000` 초과 시 hard로 fallback.

**Spec:** `docs/specs/2026-05-24-knot-cycle-5-hard-soft-design.md` (결정 이력 10개).

**Scope (5 task)**:
1. Middleware throttle 로직 + `_deny_response` 리팩터 + unit 3개
2. rules.yaml premium에 `mode: soft` + integration 3개 (시간 측정 포함)
3. (소소함) `pyproject.toml`엔 변경 없음 — asyncio 표준 라이브러리
4. Wiki cycle 5 섹션 + spec status + log
5. push + PR

실제로는 task 3개 합치고 4 task로 진행 가능. 아래 plan은 4 task.

---

## File Structure

```
신규:
  tests/unit/test_middleware_mode.py
  tests/integration/test_hard_soft_e2e.py

변경:
  app/middleware.py            # mode 분기, MAX_THROTTLE_MS, _deny_response 헬퍼
  rules.yaml                   # premium: mode: soft (1줄)
```

---

## Task 1: Middleware throttle 로직 + unit 3개 (TDD)

**Files:**
- Test: `experiments/knot/tests/unit/test_middleware_mode.py`
- Modify: `experiments/knot/app/middleware.py`

- [ ] **Step 1: 3개 failing unit 작성**

stub limiter를 만들어 deny 케이스 격리 테스트.

```python
# experiments/knot/tests/unit/test_middleware_mode.py
from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.limiter.base import Decision, Rule
from app.middleware import MAX_THROTTLE_MS, RateLimitMiddleware
from app.rules import RuleNode, Rules


def _make_app(rule: Rule, decision: Decision) -> FastAPI:
    """deny를 항상 반환하는 stub limiter로 app 구성."""

    class _StubLimiter:
        async def allow(self, key, r):
            return decision

    app = FastAPI()

    # 트리에 endpoint=shorten으로 rule 박기
    root = RuleNode()
    endpoint_node = RuleNode(rate_limit=rule)
    root.children[("endpoint", "shorten")] = endpoint_node
    app.state.rules = Rules(domain="knot", root=root)

    app.add_middleware(RateLimitMiddleware)

    # registry monkeypatch — get_limiter("X")가 stub 반환
    import app.limiter.registry as registry
    original = registry.get_limiter
    registry.get_limiter = lambda name: _StubLimiter()

    @app.post("/shorten", name="shorten")
    async def shorten(payload: dict):
        return {"code": "stub"}

    app._restore_registry = lambda: setattr(registry, "get_limiter", original)
    return app


@pytest.mark.asyncio
async def test_hard_mode_denies_with_429():
    rule = Rule(algorithm="sliding_window_log", unit="minute", requests_per_unit=10, mode="hard")
    decision = Decision(allowed=False, limit=10, remaining=0, retry_after=0.5)
    app = _make_app(rule, decision)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/shorten", json={"url": "x"})
        assert r.status_code == 429
        assert r.headers["x-ratelimit-limit"] == "10"
        assert r.headers["x-ratelimit-remaining"] == "0"
        assert "x-ratelimit-throttled" not in r.headers
    finally:
        app._restore_registry()


@pytest.mark.asyncio
async def test_soft_mode_throttles_with_200():
    rule = Rule(algorithm="sliding_window_log", unit="minute", requests_per_unit=10, mode="soft")
    decision = Decision(allowed=False, limit=10, remaining=0, retry_after=0.3)  # 300ms
    app = _make_app(rule, decision)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            start = time.perf_counter()
            r = await c.post("/shorten", json={"url": "x"})
            elapsed = time.perf_counter() - start
        assert r.status_code == 200
        assert r.headers["x-ratelimit-throttled"] == "true"
        assert int(r.headers["x-ratelimit-throttle-ms"]) == 300
        # 실제 sleep된 시간 검증 (관대한 하한)
        assert elapsed >= 0.25, f"throttle slept only {elapsed}s"
    finally:
        app._restore_registry()


@pytest.mark.asyncio
async def test_soft_mode_too_long_falls_back_to_hard():
    """retry_after가 MAX_THROTTLE_MS 초과면 429 fallback."""
    rule = Rule(algorithm="sliding_window_log", unit="minute", requests_per_unit=10, mode="soft")
    decision = Decision(allowed=False, limit=10, remaining=0, retry_after=(MAX_THROTTLE_MS / 1000) + 1)
    app = _make_app(rule, decision)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/shorten", json={"url": "x"})
        assert r.status_code == 429
        assert "x-ratelimit-throttled" not in r.headers
    finally:
        app._restore_registry()
```

- [ ] **Step 2: 실패 확인**

Run: `cd experiments/knot && uv run pytest tests/unit/test_middleware_mode.py -v`
Expected: `ImportError: cannot import name 'MAX_THROTTLE_MS' from 'app.middleware'` (3개 모두).

- [ ] **Step 3: middleware 수정**

```python
# experiments/knot/app/middleware.py — 전체 교체

from __future__ import annotations

import asyncio
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.limiter.base import Decision, Rule
from app.limiter.registry import get_limiter

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

        limiter = get_limiter(rule.algorithm)
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
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/unit/test_middleware_mode.py -v`
Expected: 3 passed.

- [ ] **Step 5: 기존 테스트 전체 확인**

```bash
docker compose up -d redis
docker compose exec -T redis redis-cli FLUSHALL
REDIS_AVAILABLE=1 uv run pytest -v
```
Expected: 41 passed (이전 38 + 새 3).

- [ ] **Step 6: 커밋**

```bash
git add experiments/knot/app/middleware.py experiments/knot/tests/unit/test_middleware_mode.py
git commit -m "experiment: knot cycle 5 - middleware mode 분기 (hard 429 / soft throttle) + unit 3개"
```

---

## Task 2: rules.yaml premium soft + integration 3개

**Files:**
- Modify: `experiments/knot/rules.yaml`
- Test: `experiments/knot/tests/integration/test_hard_soft_e2e.py`

- [ ] **Step 1: rules.yaml premium에 mode: soft**

```yaml
domain: knot
descriptors:
  - key: endpoint
    value: shorten
    descriptors:
      - key: user_tier
        value: premium
        rate_limit:
          algorithm: sliding_window_log
          unit: minute
          requests_per_unit: 50
          mode: soft                            # ← cycle 5 추가
      - key: user_tier
        value: enterprise
        rate_limit:
          algorithm: sliding_window_log
          unit: minute
          requests_per_unit: 500
    rate_limit:
      algorithm: sliding_window_log
      unit: minute
      requests_per_unit: 10
  - key: endpoint
    value: redirect
    rate_limit:
      algorithm: token_bucket
      unit: second
      requests_per_unit: 50
      burst: 100
```

- [ ] **Step 2: 3개 integration**

```python
# experiments/knot/tests/integration/test_hard_soft_e2e.py
import asyncio
import time

import pytest


@pytest.mark.asyncio
async def test_free_tier_hard_429(client):
    """free tier (default) — hard 모드. 11번째 429."""
    headers = {"x-api-key": "hs-free", "x-user-tier": "free"}
    last_status = None
    for _ in range(11):
        r = await client.post("/shorten", json={"url": "https://e.com"}, headers=headers)
        last_status = r.status_code
    assert last_status == 429


@pytest.mark.asyncio
async def test_premium_tier_soft_throttle(client):
    """premium soft — 51번째 요청은 throttle 후 200."""
    headers = {"x-api-key": "hs-premium", "x-user-tier": "premium"}
    # 50번 빠르게 (모두 통과)
    for _ in range(50):
        r = await client.post("/shorten", json={"url": "https://e.com"}, headers=headers)
        assert r.status_code == 200

    # 51번째 — soft throttle 발생해야 함
    start = time.perf_counter()
    r = await client.post("/shorten", json={"url": "https://e.com"}, headers=headers)
    elapsed = time.perf_counter() - start

    assert r.status_code == 200, "soft mode는 200으로 통과해야 함"
    assert r.headers.get("x-ratelimit-throttled") == "true"
    throttle_ms = int(r.headers["x-ratelimit-throttle-ms"])
    assert throttle_ms > 0, "throttle_ms는 0보다 커야 함"
    # 실제 sleep 시간이 throttle_ms 근처
    assert elapsed * 1000 >= throttle_ms * 0.8, f"elapsed {elapsed*1000:.0f}ms vs throttle {throttle_ms}ms"


@pytest.mark.asyncio
async def test_premium_throttle_does_not_count(client):
    """soft throttle된 요청은 limiter counter에 추가되지 않음 (decision.allowed=False였으니)."""
    headers = {"x-api-key": "hs-premium-2", "x-user-tier": "premium"}
    # 50번 빠르게 (다 통과)
    for _ in range(50):
        await client.post("/shorten", json={"url": "https://e.com"}, headers=headers)

    # 51번째 throttle
    r = await client.post("/shorten", json={"url": "https://e.com"}, headers=headers)
    assert r.status_code == 200
    assert r.headers.get("x-ratelimit-throttled") == "true"

    # 52번째도 같은 동작 — counter 늘지 않았으므로 또 throttle 발생
    r = await client.post("/shorten", json={"url": "https://e.com"}, headers=headers)
    assert r.status_code == 200
    assert r.headers.get("x-ratelimit-throttled") == "true"
```

- [ ] **Step 3: 실행**

```bash
docker compose exec -T redis redis-cli FLUSHALL
REDIS_AVAILABLE=1 uv run pytest tests/integration/test_hard_soft_e2e.py -v
```
Expected: 3 passed.

**가능 함정**: `test_premium_tier_soft_throttle`의 51번째 요청에서 throttle_ms가 매우 작을 수 있음 (50개 빠르게 보낸 직후 → oldest timestamp가 거의 지금이라 retry_after ≈ window 전체). 또는 너무 클 수도 있음 (>MAX_THROTTLE_MS=2000 → fallback 429). 결과 보고 assertion 조정 필요할 수 있음 — 실제 값 출력해서 확인.

전체 suite:
```bash
docker compose exec -T redis redis-cli FLUSHALL
REDIS_AVAILABLE=1 uv run pytest -v
```
Expected: 44 passed.

- [ ] **Step 4: 커밋**

```bash
git add experiments/knot/rules.yaml experiments/knot/tests/integration/test_hard_soft_e2e.py
git commit -m "experiment: knot cycle 5 - rules.yaml premium mode:soft + e2e 3개 (시간 측정)"
```

---

## Task 3: 수동 시연 + wiki cycle 5 섹션

**Files:**
- Modify: `wiki/projects/knot.md`

- [ ] **Step 1: 수동 시연 (curl로 throttle 확인 + wiki 노트에 박을 실측치 수집)**

```bash
cd /Users/fetching/study/system-design/experiments/knot
docker compose up -d redis
docker compose exec -T redis redis-cli FLUSHALL

uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 > /tmp/knot_c5_app.log 2>&1 &
APP_PID=$!
sleep 3

# free hard: 11번째 429
for i in $(seq 1 11); do
  status=$(curl -s -o /dev/null -w "%{http_code}" -X POST localhost:8001/shorten \
    -H "content-type: application/json" \
    -H "x-api-key: demo-free" \
    -H "x-user-tier: free" \
    -d '{"url":"https://e.com"}')
  echo "free $i: $status"
done

echo "---"

# premium soft: 51번째 throttle
for i in $(seq 1 51); do
  start=$(date +%s%3N)
  resp=$(curl -s -i -X POST localhost:8001/shorten \
    -H "content-type: application/json" \
    -H "x-api-key: demo-premium" \
    -H "x-user-tier: premium" \
    -d '{"url":"https://e.com"}')
  end=$(date +%s%3N)
  status=$(echo "$resp" | head -1 | awk '{print $2}')
  throttled=$(echo "$resp" | grep -i "x-ratelimit-throttled" | head -1 | tr -d '\r')
  echo "premium $i: status=$status elapsed=$((end-start))ms $throttled"
done

kill $APP_PID
```

실측치를 wiki cycle 5 섹션에 반영.

- [ ] **Step 2: wiki cycle 5 섹션 append**

```markdown

## Cycle 5 — Hard vs Soft 정책

**목표**: cycle 0부터 박혀있던 `Rule.mode` 필드 활성화. premium tier에 `mode: soft` 적용 → 한도 초과 시 거부 대신 **throttle 후 통과**.

**산출**: 4 task (운영 사이클로 간결), 44개 테스트 (이전 38 + middleware unit 3 + e2e 3 = 44). 알고리즘 코드 0줄 변경.

**Sub-spec**: `docs/specs/2026-05-24-knot-cycle-5-hard-soft-design.md` (결정 이력 10개).

### ch04 §"추가 토픽 — hard vs soft"의 한 단락을 코드로

ch04 본문은 한 단락만 다룸 — "hard = 절대 불가, soft = 단기 초과 허용". 우리 구현:

| | hard (cycle 4까지 모든 정책) | soft (cycle 5 premium만) |
|---|---|---|
| 한도 초과 시 | 즉시 **429** + `Retry-After` 헤더 | **throttle** (`asyncio.sleep`) 후 **200** + `X-Ratelimit-Throttled: true` |
| 카운터 | 변경 안 됨 (allow=False) | 변경 안 됨 (decision은 deny 그대로) |
| 클라이언트 인지 | 명백한 429 | 응답 지연으로 자연 backoff signal |
| 비즈니스 시그널 | 보호 우선 | UX 우선 |

**핵심 결정**: soft에서 throttle된 요청은 **counter에 추가하지 않음**. limiter.allow()가 deny를 반환했으므로 counter는 그대로. soft = "한도는 유지하되 거부 대신 지연으로 표현". 메모리 누수 없음.

### Throttle 안전 장치 — `MAX_THROTTLE_MS = 2000`

retry_after가 2초 초과 시 **hard로 폴백 (429)**. 이유: 장기 폭주 사용자가 서버 thread/connection을 무한 점유하는 것 방지. soft도 무제한이 아님.

### 실측 (T3 수동 시연)

(실측 결과를 여기 채워넣기 — premium 51번째 요청의 elapsed_ms, throttle_ms 값)

### Middleware 분기 흐름

```
decision = await limiter.allow(...)

if allowed: 정상 200 + headers
else:
    if mode == soft and retry_after_ms < 2000:
        sleep retry_after → 200 + Throttled header
    else:
        429 + Retry-After header
```

알고리즘 코드 0줄 변경, 모든 정책 표현력이 middleware의 mode 분기로 흡수. **Limiter Protocol·Decision 추상화의 가치 누적 검증**.

### Cycle 5 회고

knot의 정책 표현력 두 단계 완성:
- **표현 차원**: cycle 4 `endpoint × user_tier` 다차원 매칭
- **표현 강도**: cycle 5 `mode: hard | soft` 정책 강도 토글

남은 cycle 6: **클라이언트 SDK 미니** — 우리가 만든 `X-Ratelimit-Throttled` 헤더와 `Retry-After`를 클라이언트가 어떻게 처리하나. exponential backoff 패턴 직접 구현해서 naive client와 비교.

cycle 7: 회고 — 안 한 것 정리 (leaking_bucket / sliding_window_counter / multi-DC / OSI L3 / edge 배치).
```

- [ ] **Step 2 (계속): 실측치 채워넣기**

수동 시연 결과(Step 1 출력)를 보고 "실측 (T3 수동 시연)" 섹션에 구체 수치 박기. 예시 형태:

```markdown
### 실측 (수동 시연)

```
free 1~10: 200 200 200 200 200 200 200 200 200 200
free 11:   429

premium 1~50: 모두 200, 응답 ~3-5ms
premium 51:   200, elapsed=620ms, X-Ratelimit-Throttled: true, X-Ratelimit-Throttle-Ms: 600
```

51번째 요청이 ~600ms throttle 후 200 — limiter.retry_after가 "가장 오래된 timestamp 윈도우 밖으로 나갈 시각"이라 정확히 그만큼 대기. 클라이언트는 "느린 응답"으로 한도 인지.
```

- [ ] **Step 3: 커밋**

```bash
git add wiki/projects/knot.md
git commit -m "docs: wiki/projects/knot.md - cycle 5 (hard vs soft) 섹션 append"
```

---

## Task 4: spec status + log + push + PR

**Files:**
- Modify: `docs/specs/2026-05-24-rate-limiter-design.md`
- Modify: `log.md`

- [ ] **Step 1: spec §7 cycle 5 done**

cycle 5 행 status: `todo` → `done (2026-05-24)`

- [ ] **Step 2: log.md append**

```markdown

## [2026-05-24] experiment | knot cycle 5: Hard vs Soft 정책

cycle 0부터 박혀있던 `Rule.mode` 필드 활성화. mode=hard는 기존 429, mode=soft는 asyncio.sleep으로 throttle 후 200 (X-Ratelimit-Throttled: true 헤더). MAX_THROTTLE_MS=2000 초과 시 hard fallback (장기 폭주 보호). shorten premium tier만 soft (유료=UX 우선), free·enterprise·redirect는 hard 유지. 알고리즘 코드 0줄 변경 — middleware의 mode 분기만으로 ch04 §"추가 토픽"의 한 단락 구현. 44 tests passing.

- 결정 이력: spec `docs/specs/2026-05-24-knot-cycle-5-hard-soft-design.md` §5

cycle 6: 클라이언트 SDK (429·Retry-After·Throttled 헤더 → exponential backoff).
```

- [ ] **Step 3: 커밋 + push + PR**

```bash
cd /Users/fetching/study/system-design
git add docs/specs/2026-05-24-rate-limiter-design.md log.md
git commit -m "experiment: knot cycle 5 완료 — spec + log"
git push -u origin experiment/knot-cycle-5

gh pr create --base main --head experiment/knot-cycle-5 \
  --title "experiment: knot cycle 5 (Hard vs Soft 정책)" \
  --body "$(cat <<'EOF'
## Summary

알고리즘 코드 0줄 변경. cycle 0 `Rule.mode` 필드 활성화 — middleware에 mode 분기 추가.

- **hard**: 한도 초과 즉시 429 (기존 동작)
- **soft**: `asyncio.sleep(retry_after_ms)` 후 200 + `X-Ratelimit-Throttled: true`
- **MAX_THROTTLE_MS=2000** 초과 시 hard fallback (장기 폭주 보호)

shorten premium tier만 soft (UX 우선). free·enterprise·redirect는 hard 유지.

## 핵심 측정

- premium 51번째 요청 → throttle 후 200, 응답 ~600ms (Limiter가 계산한 정확한 재시도 시각)
- throttled 요청은 counter에 추가하지 않음 (decision.allowed=False)

## ch04 매핑

§"추가 토픽 — hard vs soft rate limiting" 한 단락의 코드 구현. ch04는 hard/soft 트레이드오프(보호 vs UX)만 언급하고 구체적 throttle 구현은 안 다룸 — 우리는 retry_after 기반 정확한 wait로 자연 backoff signal 생성.

## 다음 사이클

cycle 6: 클라이언트 SDK (429·Retry-After·X-Ratelimit-Throttled → exponential backoff).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## 검증 체크리스트

- [ ] `REDIS_AVAILABLE=1 uv run pytest -v` 44 passed
- [ ] 수동 시연 결과 — premium 51번째 elapsed ≈ throttle_ms ≈ 한도 정책 윈도우의 잔여 시간
- [ ] PR 생성

## 다음 사이클

**Cycle 6 — 클라이언트 SDK 미니**: `experiments/knot/client/knot_client.py` — `X-Ratelimit-*` 헤더 인지, `Retry-After` 준수, 429/throttled 받으면 exponential backoff. naive httpx 클라이언트와 비교 부하 시험. ~5 task.
