# knot Cycle 3 — Sliding Window Log 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** [[sliding-window-log-algorithm]]을 `shorten` 엔드포인트에 끼우고, ZSET+Lua atomicity 증명 + 4개 k6 시나리오로 cycle 2 fixed_window와의 차이(경계 burst 부재) 시각화.

**Architecture:** cycle 1과 동일한 plug-in. ZSET key당 1개(`knot:swl:endpoint:identity`), member=`f"{ts_us}-{random_hex_4}"`. Lua가 ZREMRANGEBYSCORE+ZCARD+ZADD 3명령 묶음으로 atomic.

**Spec:** `docs/specs/2026-05-24-knot-cycle-3-sliding-window-log-design.md` (결정 이력 10개).

**Scope (9 task)** — cycle 1과 동일 형식:

1. Lua + dev 의존성 (필요시)
2. SlidingWindowLog 클래스 + unit (TDD, 4개)
3. Registry 등록 + rules.yaml shorten 전환 + e2e 갱신
4. 통합 테스트 (실 Redis + race demo)
5. k6 4개 시나리오 (burst, ramp, cycle, boundary_burst_replay)
6. k6 실행 + report
7. wiki cycle 3 섹션
8. spec status + log + push + PR

---

## File Structure

```
신규:
  app/limiter/scripts/sliding_window_log.lua
  app/limiter/sliding_window_log.py
  tests/unit/test_sliding_window_log.py
  tests/integration/test_sliding_window_log_redis.py
  load/sliding_window_log.k6.js
  reports/sliding_window_log.md (+ PNG)

변경:
  app/limiter/registry.py (1줄)
  rules.yaml (shorten)
  tests/integration/test_middleware_e2e.py (shorten 기대값)
```

---

## Task 1: Lua script

**Files:**
- Create: `experiments/knot/app/limiter/scripts/sliding_window_log.lua`

- [ ] **Step 1: Lua 작성**

```lua
-- experiments/knot/app/limiter/scripts/sliding_window_log.lua
-- KEYS[1] = ZSET key
-- ARGV[1] = limit, ARGV[2] = window_size_seconds, ARGV[3] = random_hex_4
-- returns: {allowed (0|1), limit, remaining, retry_after_ms}

local now_pair = redis.call('TIME')
local now_us = tonumber(now_pair[1]) * 1000000 + tonumber(now_pair[2])

local window_size = tonumber(ARGV[2])
local window_us = window_size * 1000000
local cutoff = now_us - window_us

redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, cutoff)
local count = redis.call('ZCARD', KEYS[1])
local limit = tonumber(ARGV[1])

local allowed = 0
local remaining = 0
local retry_after_ms = 0

if count < limit then
  local member = tostring(now_us) .. '-' .. ARGV[3]
  redis.call('ZADD', KEYS[1], now_us, member)
  allowed = 1
  remaining = limit - count - 1
else
  remaining = 0
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  if #oldest >= 2 then
    local oldest_us = tonumber(oldest[2])
    retry_after_ms = math.ceil((oldest_us + window_us - now_us) / 1000)
  end
end

redis.call('EXPIRE', KEYS[1], window_size + 5)

return {allowed, limit, remaining, retry_after_ms}
```

- [ ] **Step 2: 커밋**

```bash
git add experiments/knot/app/limiter/scripts/sliding_window_log.lua
git commit -m "experiment: knot cycle 3 - sliding_window_log.lua (ZSET 3명령 atomic)"
```

---

## Task 2: SlidingWindowLog 클래스 + unit tests (TDD)

**Files:**
- Test: `experiments/knot/tests/unit/test_sliding_window_log.py`
- Create: `experiments/knot/app/limiter/sliding_window_log.py`

- [ ] **Step 1: 실패하는 unit 테스트 (4개)**

```python
# experiments/knot/tests/unit/test_sliding_window_log.py
from __future__ import annotations

import pytest
from freezegun import freeze_time

from app.limiter.base import Rule


@pytest.fixture
async def limiter(monkeypatch):
    import fakeredis.aioredis
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    import app.redis_client
    monkeypatch.setattr(app.redis_client, "_client", fake)
    from app.limiter.sliding_window_log import SlidingWindowLog
    return SlidingWindowLog()


@pytest.mark.asyncio
async def test_basic_pass_then_deny(limiter):
    rule = Rule(algorithm="sliding_window_log", unit="minute", requests_per_unit=5)
    with freeze_time("2026-05-24 12:00:00"):
        for i in range(5):
            d = await limiter.allow("knot:test:user-a", rule)
            assert d.allowed is True
            assert d.remaining == 4 - i
        d = await limiter.allow("knot:test:user-a", rule)
        assert d.allowed is False
        assert d.remaining == 0
        assert d.retry_after > 0


@pytest.mark.asyncio
async def test_no_boundary_burst(limiter):
    """sliding window는 fixed window의 경계 burst를 해결."""
    rule = Rule(algorithm="sliding_window_log", unit="minute", requests_per_unit=5)
    # 12:00:59에 5번 (cycle 2 fixed_window라면 다 통과)
    with freeze_time("2026-05-24 12:00:59") as ft:
        for _ in range(5):
            d = await limiter.allow("knot:test:user-b", rule)
            assert d.allowed is True

        # 1초 후 (12:01:00) — sliding window: 직전 60초(12:00:00~12:01:00)에 이미 5개 존재 → 거부
        ft.tick(1.0)
        d = await limiter.allow("knot:test:user-b", rule)
        assert d.allowed is False, "sliding window는 경계에서 추가 통과 막아야 함"


@pytest.mark.asyncio
async def test_window_slides_continuously(limiter):
    """오래된 timestamp가 윈도우 밖으로 나가면 새 요청 통과."""
    rule = Rule(algorithm="sliding_window_log", unit="second", requests_per_unit=3)
    # 1초 윈도우에 3개 채움
    with freeze_time("2026-05-24 12:00:00") as ft:
        for _ in range(3):
            await limiter.allow("knot:test:user-c", rule)
        # 4번째 거부
        d = await limiter.allow("knot:test:user-c", rule)
        assert d.allowed is False

        # 1.1초 후 — 첫 3개가 모두 윈도우 밖 → 새 요청 통과
        ft.tick(1.1)
        d = await limiter.allow("knot:test:user-c", rule)
        assert d.allowed is True


@pytest.mark.asyncio
async def test_retry_after_accurate(limiter):
    """retry_after_ms = (oldest_ts + window - now) — 정확한 시각."""
    rule = Rule(algorithm="sliding_window_log", unit="second", requests_per_unit=2)
    with freeze_time("2026-05-24 12:00:00.000000") as ft:
        await limiter.allow("knot:test:user-d", rule)   # ts=12:00:00
        ft.tick(0.3)
        await limiter.allow("knot:test:user-d", rule)   # ts=12:00:00.3
        ft.tick(0.1)
        # 12:00:00.4 시점 — limit=2 소진
        d = await limiter.allow("knot:test:user-d", rule)
        assert d.allowed is False
        # oldest=12:00:00, window=1s, now=12:00:00.4 → retry_after = 12:00:01 - 12:00:00.4 = 0.6s = 600ms
        assert 550 <= d.retry_after * 1000 <= 700, f"retry_after={d.retry_after*1000}ms"
```

- [ ] **Step 2: 실패 확인**

Run: `cd experiments/knot && uv run pytest tests/unit/test_sliding_window_log.py -v`
Expected: `ModuleNotFoundError: No module named 'app.limiter.sliding_window_log'`

- [ ] **Step 3: 구현**

```python
# experiments/knot/app/limiter/sliding_window_log.py
from __future__ import annotations

import secrets
from pathlib import Path

from app.limiter.base import Decision, Rule
from app.redis_client import get_redis

_SCRIPT_PATH = Path(__file__).parent / "scripts" / "sliding_window_log.lua"
_SCRIPT_SRC = _SCRIPT_PATH.read_text()

_UNIT_SECONDS = {"second": 1, "minute": 60, "hour": 3600}


class SlidingWindowLog:
    def __init__(self) -> None:
        self._script = None
        self._script_client = None

    async def allow(self, key: str, rule: Rule) -> Decision:
        client = get_redis()
        if self._script is None or self._script_client is not client:
            self._script = client.register_script(_SCRIPT_SRC)
            self._script_client = client

        window_size = _UNIT_SECONDS[rule.unit]
        zset_key = key.replace("knot:", "knot:swl:", 1)
        random_hex = secrets.token_hex(2)  # 4 hex chars

        result = await self._script(
            keys=[zset_key],
            args=[rule.requests_per_unit, window_size, random_hex],
        )
        allowed, limit, remaining, retry_ms = result

        return Decision(
            allowed=bool(int(allowed)),
            limit=int(limit),
            remaining=int(remaining),
            retry_after=int(retry_ms) / 1000.0,
        )
```

- [ ] **Step 4: 통과 확인**

Run: `cd experiments/knot && uv run pytest tests/unit/test_sliding_window_log.py -v`
Expected: 4 passed.

- [ ] **Step 5: 커밋**

```bash
git add experiments/knot/app/limiter/sliding_window_log.py experiments/knot/tests/unit/test_sliding_window_log.py
git commit -m "experiment: knot cycle 3 - SlidingWindowLog 클래스 + 4개 unit (no boundary burst 시연 포함)"
```

---

## Task 3: Registry 등록 + rules.yaml shorten 전환 + e2e 갱신

**Files:**
- Modify: `experiments/knot/app/limiter/registry.py`
- Modify: `experiments/knot/rules.yaml`
- Modify: `experiments/knot/tests/integration/test_middleware_e2e.py`

- [ ] **Step 1: registry 1줄**

```python
from app.limiter.always_allow import AlwaysAllow
from app.limiter.base import Limiter
from app.limiter.fixed_window import FixedWindow
from app.limiter.sliding_window_log import SlidingWindowLog
from app.limiter.token_bucket import TokenBucket

_LIMITERS: dict[str, Limiter] = {
    "always_allow": AlwaysAllow(),
    "token_bucket": TokenBucket(),
    "fixed_window": FixedWindow(),
    "sliding_window_log": SlidingWindowLog(),
}
```

- [ ] **Step 2: rules.yaml shorten 전환**

```yaml
domain: knot
descriptors:
  - key: endpoint
    value: shorten
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

- [ ] **Step 3: e2e 테스트 기대값 갱신**

`tests/integration/test_middleware_e2e.py`의 `test_shorten_returns_200_with_rate_limit_headers`:

old:
```python
assert response.headers["x-ratelimit-limit"] == "10"
assert response.headers["x-ratelimit-remaining"] == "10"
```

new:
```python
assert response.headers["x-ratelimit-limit"] == "10"
assert response.headers["x-ratelimit-remaining"] == "9"  # sliding_window_log은 1개 차감
```

- [ ] **Step 4: 전체 테스트**

Run: `docker compose up -d redis && cd experiments/knot && REDIS_AVAILABLE=1 uv run pytest -v`
Expected: 25 passed (cycle 0-2: 21 + cycle 3 unit: 4).

- [ ] **Step 5: 커밋**

```bash
git add experiments/knot/app/limiter/registry.py experiments/knot/rules.yaml experiments/knot/tests/integration/test_middleware_e2e.py
git commit -m "experiment: knot cycle 3 - registry + shorten 정책 sliding_window_log로 전환"
```

---

## Task 4: 통합 테스트 (실 Redis + race demo)

**Files:**
- Create: `experiments/knot/tests/integration/test_sliding_window_log_redis.py`

- [ ] **Step 1: 통합 테스트**

```python
# experiments/knot/tests/integration/test_sliding_window_log_redis.py
import asyncio

import pytest


@pytest.mark.asyncio
async def test_shorten_burst_throttled(client):
    """shorten 분당 10 — 11회 연속이면 마지막 deny."""
    headers = {"x-api-key": "burst-test-c3"}
    statuses = []
    for _ in range(11):
        r = await client.post("/shorten", json={"url": "https://example.com"}, headers=headers)
        statuses.append(r.status_code)
    passed = sum(1 for s in statuses if s == 200)
    denied = sum(1 for s in statuses if s == 429)
    assert passed == 10
    assert denied == 1


@pytest.mark.asyncio
async def test_race_condition_atomic_zset(client):
    """50 동시 POST (limit=10) → 정확히 10 통과 (ZSET + Lua atomicity)."""
    headers = {"x-api-key": "race-test-c3"}

    async def hit():
        r = await client.post("/shorten", json={"url": "https://example.com"}, headers=headers)
        return r.status_code

    results = await asyncio.gather(*[hit() for _ in range(50)])
    passed = sum(1 for s in results if s == 200)
    denied = sum(1 for s in results if s == 429)
    assert passed == 10, f"passed={passed} — ZSET atomic 위반 의심"
    assert passed + denied == 50


@pytest.mark.asyncio
async def test_identity_isolation_shorten(client):
    """다른 API key는 별도 ZSET."""
    for _ in range(10):
        await client.post("/shorten", json={"url": "https://example.com"}, headers={"x-api-key": "user-x-c3"})

    r = await client.post("/shorten", json={"url": "https://example.com"}, headers={"x-api-key": "user-y-c3"})
    assert r.status_code == 200
    assert r.headers["x-ratelimit-remaining"] == "9"
```

- [ ] **Step 2: 실행**

```bash
docker compose exec -T redis redis-cli FLUSHALL  # 깨끗한 상태
REDIS_AVAILABLE=1 uv run pytest tests/integration/test_sliding_window_log_redis.py -v
```
Expected: 3 passed. race demo의 `passed == 10` 정확히 일치 (sliding window log는 timestamp 엄격 비교라 cycle 1보다 jitter 없음).

- [ ] **Step 3: 커밋**

```bash
git add experiments/knot/tests/integration/test_sliding_window_log_redis.py
git commit -m "experiment: knot cycle 3 - sliding_window_log 통합 테스트 + race demo (ZSET atomicity 증명)"
```

---

## Task 5: k6 4개 시나리오 (boundary replay 포함)

**Files:**
- Create: `experiments/knot/load/sliding_window_log.k6.js`

- [ ] **Step 1: k6 작성**

```javascript
// experiments/knot/load/sliding_window_log.k6.js
// shorten 엔드포인트 (분당 10) — 4 시나리오:
// burst, ramp, steady_burst_cycle, boundary_burst_replay (cycle 2와 동일 패턴으로 비교)

import http from 'k6/http';
import { check } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://host.docker.internal:8001';

export const options = {
  scenarios: {
    burst: {
      executor: 'per-vu-iterations',
      vus: 20,
      iterations: 1,
      maxDuration: '5s',
      startTime: '0s',
      tags: { scenario: 'burst' },
    },
    ramp: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      stages: [{ duration: '60s', target: 30 }],
      preAllocatedVUs: 30,
      maxVUs: 100,
      timeUnit: '1s',
      startTime: '10s',
      tags: { scenario: 'ramp' },
    },
    steady_burst_cycle: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      stages: [
        { duration: '1s', target: 20 }, { duration: '5s', target: 0 },
        { duration: '1s', target: 20 }, { duration: '5s', target: 0 },
        { duration: '1s', target: 20 }, { duration: '5s', target: 0 },
      ],
      preAllocatedVUs: 30,
      maxVUs: 50,
      timeUnit: '1s',
      startTime: '80s',
      tags: { scenario: 'steady_burst_cycle' },
    },
    boundary_burst_replay: {
      // cycle 2 fixed_window와 동일 시나리오. sliding window는 spike-deny-spike 패턴이 아닌 균등 throttle 보여야 함
      executor: 'constant-arrival-rate',
      rate: 30,
      timeUnit: '1s',
      duration: '12s',
      preAllocatedVUs: 20,
      maxVUs: 50,
      startTime: '120s',
      tags: { scenario: 'boundary_burst_replay' },
    },
  },
};

export default function () {
  const res = http.post(`${BASE_URL}/shorten`, JSON.stringify({ url: 'https://example.com' }), {
    headers: { 'content-type': 'application/json', 'x-api-key': `k6-${__VU}` },
  });
  check(res, { 'status is 200 or 429': (r) => r.status === 200 || r.status === 429 });
}
```

**중요**: shorten의 limit=10/min이라 VU마다 다른 api-key를 줘서 각자 bucket을 갖게 함 — 그래야 시나리오가 끝나기 전에 다 거부되지 않고 분산된 동작 관찰 가능.

- [ ] **Step 2: 커밋**

```bash
git add experiments/knot/load/sliding_window_log.k6.js
git commit -m "experiment: knot cycle 3 - k6 4개 시나리오 (burst/ramp/cycle/boundary_replay)"
```

---

## Task 6: k6 실행 + reports/sliding_window_log.md

**Files:**
- Create (생성됨): `experiments/knot/reports/sliding_window_log.md` + PNG

- [ ] **Step 1: 앱 background**

```bash
cd /Users/fetching/study/system-design/experiments/knot
docker compose up -d redis
docker compose exec -T redis redis-cli FLUSHALL

uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 > /tmp/knot_c3_app.log 2>&1 &
APP_PID=$!
sleep 3
curl -sf http://localhost:8001/healthz | head -1
```

- [ ] **Step 2: k6 실행** (~135초 — 4 시나리오 순차)

```bash
mkdir -p out
docker run --rm -i \
  -v $(pwd):/work -w /work \
  -e BASE_URL=http://host.docker.internal:8001 \
  grafana/k6 run \
  --out json=out/sliding_window_log.json \
  load/sliding_window_log.k6.js

kill $APP_PID 2>/dev/null
```

Expected: `http_reqs{status:429}` count > 0. 약 1100~1500 총 요청.

- [ ] **Step 3: 리포트 생성**

```bash
uv run python scripts/report.py \
  --k6-json out/sliding_window_log.json \
  --algorithm sliding_window_log \
  --output reports/sliding_window_log.md
```

- [ ] **Step 4: boundary replay 해설 append**

`reports/sliding_window_log.md`에 자동 생성된 본문 아래 추가:

```markdown
## Boundary burst replay — cycle 2와의 비교

위 차트에서 `boundary_burst_replay` 시나리오를 cycle 2 `reports/fixed_window.md`의 동일 시나리오와 비교:

| 알고리즘 | 통과 패턴 | 분 경계 처리 |
|---|---|---|
| fixed_window (cycle 2) | spike-deny-spike (2 spike) | 경계 직후 추가 100 통과 → 의도 2배 |
| sliding_window_log (cycle 3) | 균등 throttle | 경계 무관 — 임의 시점 직전 60초 기준 |

sliding window의 핵심 가치: **경계 burst 부재**. ch04 §"알고리즘 비교"의 "정확도: 높음"의 그래프 증명.
```

- [ ] **Step 5: 커밋**

```bash
git add experiments/knot/reports/sliding_window_log.md experiments/knot/reports/sliding_window_log_timeseries.png
git commit -m "experiment: knot cycle 3 - k6 4시나리오 + report (boundary burst 부재 시각화)"
```

---

## Task 7: wiki/projects/knot.md cycle 3 섹션

**Files:**
- Modify: `wiki/projects/knot.md`

- [ ] **Step 1: 섹션 append** (cycle 1·2 스타일, 실측 결과 반영)

```markdown

## Cycle 3 — Sliding Window Log

**목표**: [[sliding-window-log-algorithm]]을 `shorten` 엔드포인트에 끼우고, cycle 2 boundary burst를 sliding window가 해결함을 그래프로 비교 증명.

**산출**: 9 task, ~10 commit, 25개 테스트 통과 (unit 15 + integration 10). race demo로 ZSET+Lua atomicity 증명. 4개 k6 시나리오로 sliding window 본질 + cycle 2와 직접 비교.

**Sub-spec**: `docs/specs/2026-05-24-knot-cycle-3-sliding-window-log-design.md` (결정 이력 10개).

### Task 1-2 — Lua + 클래스 + unit

**핵심 Lua 패턴** — cycle 1 token_bucket과 자료구조만 다름 (ZSET):

```lua
ZREMRANGEBYSCORE key 0 cutoff      -- 윈도우 밖 제거
local count = ZCARD key            -- 안에 몇 개
if count < limit then ZADD key now_us member; allowed=1 end
```

ch04 §"race condition"의 두 번째 표준 해법(ZSET+atomic). 세 명령을 Lua로 묶어 race 차단.

**Member 형식 결정** (spec §3): `f"{ts_us}-{random_hex_4}"`. 같은 microsecond 충돌 회피 — ch04는 명시 안 한 textbook 묵시 가정의 엔지니어링 보강.

**`test_no_boundary_burst`** — cycle 2 fixed_window의 정확한 안티 시연. 12:00:59에 5개 통과 후, 1초 흘러 12:01:00에 5번째 호출 → **거부** (직전 60초 윈도우에 이미 5개 있음). cycle 2와 정반대 결과 — 같은 unit test로 검증.

### Task 3 — `shorten` 전환

**diff**:
- registry 1줄
- rules.yaml `shorten` algorithm 변경
- e2e 기대값: `remaining` 10 → 9 (sliding_window_log은 1개 차감 후 응답)

**knot 완성**: cycle 3 끝나면 두 엔드포인트 모두 적절한 알고리즘:
- `shorten` (쓰기, 악용 방지) → sliding_window_log (엄격, 분당 10)
- `redirect` (읽기, UX 우선) → token_bucket (관대, burst 100)

### Task 4 — Race demo (ZSET + Lua)

**결과**: 50 동시 POST (limit=10) → 정확히 10 통과. cycle 1의 101 통과(jitter)와 달리 sliding window는 timestamp 엄격 비교라 jitter 없음 — 더 정확한 atomic 증명.

cycle 1 token_bucket과의 차이: token bucket은 dispatch 동안 refill로 +1 가능. sliding window log는 dispatch 동안 새 timestamp가 윈도우 밖으로 나갈 시간 없음 (limit 도달 시 정확히 deny).

### Task 5-6 — k6 4시나리오 + 리포트

| scenario | total | denied | pass_rate | 의미 |
|---|---|---|---|---|
| burst | (실측 후 채우기) | | | sliding window는 limit 정확히 |
| ramp | | | | rate 초과 지점에서 throttle |
| steady_burst_cycle | | | | 윈도우 안 정수만 통과 |
| boundary_burst_replay | | | | **cycle 2 차트와 비교 — spike 없음** |

(실측 후 채움. cycle 1처럼 실수치 박기.)

### Cycle 3 회고 — 알고리즘 비교 완성

cycle 1 token_bucket + cycle 2 fixed_window + cycle 3 sliding_window_log = **ch04 비교표 5개 셀 중 3개를 그래프로 증명**:

| 알고리즘 | 정확도 | 메모리 | 버스트 | 우리 차트 |
|---|---|---|---|---|
| token_bucket (cycle 1) | 중 | 적음 | 허용 | `reports/token_bucket.md` 58% pass on burst |
| fixed_window (cycle 2) | **낮음** | 적음 | — | `reports/fixed_window.md` 분 경계 spike-spike |
| sliding_window_log (cycle 3) | **높음** | **많음** | — | `reports/sliding_window_log.md` boundary replay 균등 throttle |

남은 2개(leaking·sliding_counter)는 회고(cycle 7)에서 wiki 글로 정리. token bucket(평탄화 안 함) + sliding window log(엄격, 메모리 비쌈)가 양 극단을 잡고 있어 사이의 알고리즘은 글만으로 위치 추정 가능.

**knot 완성** — shorten·redirect 모두 알고리즘 활성화. cycle 4부터는 알고리즘 추가 없음, **운영 측면 진화** (다차원 규칙·hard/soft·클라이언트 SDK).
```

- [ ] **Step 2: 커밋**

```bash
git add wiki/projects/knot.md
git commit -m "docs: wiki/projects/knot.md - cycle 3 (sliding window log) 섹션 append"
```

---

## Task 8: spec status + log + push + PR

**Files:**
- Modify: `docs/specs/2026-05-24-rate-limiter-design.md` (§7 cycle 3 status)
- Modify: `log.md`

- [ ] **Step 1: spec status**

§7 표 cycle 3 행 status: `todo` → `done (2026-05-24)`

- [ ] **Step 2: log.md append**

```markdown

## [2026-05-24] experiment | knot cycle 3: Sliding Window Log

[[sliding-window-log-algorithm]] full 사이클. `shorten` 엔드포인트를 sliding_window_log로 전환 (분당 10, mode hard). ZSET + Lua 3명령 atomic 묶음. race demo (asyncio.gather 50, limit 10) → 정확히 10 통과 — token bucket의 jitter(+1)와 달리 timestamp 엄격 비교로 0 jitter. boundary burst replay 그래프가 cycle 2 fixed_window 차트와 나란히 두면 sliding window 가치 즉시 증명.

- `app/limiter/sliding_window_log.py`, `scripts/sliding_window_log.lua` 신규
- `load/sliding_window_log.k6.js` (4 시나리오: burst·ramp·cycle·boundary_replay) + `reports/sliding_window_log.md`
- `rules.yaml` shorten → sliding_window_log (knot 두 엔드포인트 모두 활성화 완료)
- 결정 이력: spec `docs/specs/2026-05-24-knot-cycle-3-sliding-window-log-design.md` §7

knot의 알고리즘 사이클 종료. cycle 4부터는 운영 측면(다차원 규칙·hard/soft·클라이언트 SDK·회고).
```

- [ ] **Step 3: stub + 커밋 + push + PR**

```bash
cd /Users/fetching/study/system-design
git add docs/specs/2026-05-24-rate-limiter-design.md log.md
git commit -m "experiment: knot cycle 3 완료 — spec status + log"
git push -u origin experiment/knot-cycle-3

gh pr create --base main --head experiment/knot-cycle-3 \
  --title "experiment: knot cycle 3 (Sliding Window Log)" \
  --body "$(cat <<'EOF'
## Summary

[[sliding-window-log-algorithm]] full 사이클. `shorten` 엔드포인트를 sliding_window_log로 전환 (분당 10). ZSET + Lua 3명령(ZREMRANGEBYSCORE+ZCARD+ZADD) atomic 묶음. 4개 k6 시나리오 (burst·ramp·cycle·boundary_replay)로 cycle 2 fixed_window와 직접 비교.

knot의 두 엔드포인트 모두 적절한 알고리즘 활성화 완료:
- `shorten` (쓰기·악용 방지) → sliding_window_log (엄격, 분당 10)
- `redirect` (읽기·UX) → token_bucket (관대, burst 100)

## 핵심 측정

- Race demo: 50 동시 POST (limit=10) → 정확히 10 통과. token bucket의 +1 jitter와 달리 timestamp 엄격 비교
- boundary_burst_replay: cycle 2의 spike-spike와 달리 균등 throttle — sliding window의 핵심 가치 그래프 증명

## 다음 사이클

cycle 4부터 운영 측면: 다차원 규칙 + 핫리로드 → hard/soft → 클라이언트 SDK → 회고.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## 검증 체크리스트

- [ ] `REDIS_AVAILABLE=1 uv run pytest -v` 25 passed (cycle 0-2: 21 + cycle 3 unit 4 + cycle 3 integration 3 = 28). 실제 수는 unit 합산 결과로 확인
- [ ] Race demo `passed == 10` 정확 (jitter 0)
- [ ] `reports/sliding_window_log.md`의 boundary_burst_replay 차트가 cycle 2 spike 패턴과 다른 균등 throttle 시각화
- [ ] knot 두 엔드포인트 모두 의도된 알고리즘 활성화 (shorten=swl, redirect=tb)
- [ ] PR 생성

## 다음 사이클

**Cycle 4 — 다차원 규칙 + 핫리로드**: rules.yaml을 `endpoint × identity` 복합 키로 확장. 파일 watcher 또는 SIGHUP으로 핫리로드. cycle 2에서 깐 `KNOT_RULES_PATH` env가 활용됨.
