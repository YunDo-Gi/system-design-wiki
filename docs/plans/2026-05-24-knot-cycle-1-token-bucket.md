# knot Cycle 1 — Token Bucket 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** [[token-bucket-algorithm]]을 knot의 plug-in으로 끼우고, k6 부하 실측으로 ch04 비교표의 "버스트 허용" 시그니처를 시각화. 동시에 k6+matplotlib 리포트 도구 chain을 1회 셋업해 cycle 2~5가 같은 도구로 가볍게 굴러가게 한다.

**Architecture:** Lua script(`redis.call('TIME')` 내장) + HASH(tokens, last_refill) + EVALSHA. 알고리즘은 cycle 0의 `Limiter` Protocol에 모듈로 끼움. 통합 테스트가 race condition(asyncio.gather 100 동시)으로 atomicity 직접 증명. k6 시나리오 3종(burst·ramp·cycle), matplotlib 리포트는 알고리즘 무관 스크립트로.

**Tech Stack:** Python 3.12 + redis-py(async) + Lua + fakeredis + freezegun + pytest. k6(docker) + pandas + matplotlib.

**Spec:** `docs/specs/2026-05-24-knot-cycle-1-token-bucket-design.md` (결정 이력 §7 포함).

---

## File Structure

신규/변경 파일은 spec §8 참조. 핵심:

- `app/limiter/token_bucket.py` — Limiter 구현 (Lua 로드 + register_script)
- `app/limiter/scripts/token_bucket.lua` — atomic 알고리즘 본체
- `tests/unit/test_token_bucket.py` — fakeredis + freezegun
- `tests/integration/test_token_bucket_redis.py` — 실 Redis + race demo
- `load/token_bucket.k6.js` — burst·ramp·cycle 시나리오
- `scripts/report.py` — k6 JSON → matplotlib → md (알고리즘 무관)
- `reports/token_bucket.md` + 3개 PNG — 생성물

**책임 분담**

- `token_bucket.lua` — atomic + 시간 측정 + 리필 + 차감. Python에서 import만.
- `token_bucket.py` — Script 객체 캐시 + rule → ARGV 변환 + Decision 변환.
- `scripts/report.py` — k6 결과 처리 전담. 알고리즘 이름·시나리오 메타만 인자로 받음. cycle 2~5 재사용.

---

## Task 1: Lua script + 새 dev 의존성

**Files:**
- Create: `experiments/knot/app/limiter/scripts/__init__.py` (빈 파일)
- Create: `experiments/knot/app/limiter/scripts/token_bucket.lua`
- Modify: `experiments/knot/pyproject.toml` (dev deps 추가)

- [ ] **Step 1: 디렉터리 + `__init__.py`**

```bash
mkdir -p experiments/knot/app/limiter/scripts
touch experiments/knot/app/limiter/scripts/__init__.py
```

- [ ] **Step 2: `token_bucket.lua` 작성**

```lua
-- KEYS[1] = bucket key
-- ARGV[1] = capacity (int), ARGV[2] = refill_rate (tokens/sec, float), ARGV[3] = cost (int)
-- returns: {allowed (0|1), remaining (int floor), retry_after_ms (int)}

local now_pair = redis.call('TIME')
local now = tonumber(now_pair[1]) + tonumber(now_pair[2]) / 1e6

local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])

local data = redis.call('HMGET', KEYS[1], 'tokens', 'last_refill')
local tokens = tonumber(data[1]) or capacity
local last = tonumber(data[2]) or now

local elapsed = math.max(0, now - last)
tokens = math.min(capacity, tokens + elapsed * rate)

local allowed = 0
local retry_after = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
else
  retry_after = math.ceil((cost - tokens) / rate * 1000)
end

redis.call('HMSET', KEYS[1], 'tokens', tokens, 'last_refill', now)
redis.call('EXPIRE', KEYS[1], math.ceil(capacity / rate * 2))

return {allowed, math.floor(tokens), retry_after}
```

- [ ] **Step 3: `pyproject.toml`에 dev deps 추가**

기존 `[dependency-groups] dev = [...]` 리스트에 추가:

```toml
[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
    "fakeredis>=2.21",
    "freezegun>=1.4",
    "pandas>=2.2",
    "matplotlib>=3.8",
]
```

- [ ] **Step 4: `uv sync`**

Run: `cd experiments/knot && uv sync`
Expected: 새 패키지 설치 성공.

- [ ] **Step 5: 커밋**

```bash
git add experiments/knot/app/limiter/scripts experiments/knot/pyproject.toml experiments/knot/uv.lock
git commit -m "experiment: knot cycle 1 - token_bucket.lua + dev deps (freezegun, pandas, matplotlib)"
```

---

## Task 2: TokenBucket limiter 클래스 (TDD)

**Files:**
- Test: `experiments/knot/tests/unit/test_token_bucket.py`
- Create: `experiments/knot/app/limiter/token_bucket.py`

- [ ] **Step 1: 실패하는 unit 테스트 작성** (5개 핵심 시나리오)

```python
# experiments/knot/tests/unit/test_token_bucket.py
from __future__ import annotations

import pytest
from freezegun import freeze_time

from app.limiter.base import Rule


@pytest.fixture
def rule():
    # capacity=10, rate=5 tokens/sec
    return Rule(algorithm="token_bucket", unit="second", requests_per_unit=5, burst=10)


@pytest.fixture
async def limiter(monkeypatch):
    """fakeredis-backed TokenBucket."""
    import fakeredis.aioredis
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)

    # Patch get_redis to return fake
    import app.redis_client
    monkeypatch.setattr(app.redis_client, "_client", fake)

    from app.limiter.token_bucket import TokenBucket
    return TokenBucket()


@pytest.mark.asyncio
async def test_first_call_initializes_full_bucket(limiter, rule):
    d = await limiter.allow("knot:redirect:1.2.3.4", rule)
    assert d.allowed is True
    assert d.limit == 10
    assert d.remaining == 9  # 10 - 1 cost


@pytest.mark.asyncio
async def test_burst_absorbs_capacity_then_denies(limiter, rule):
    with freeze_time("2026-05-24 12:00:00"):
        for _ in range(10):
            d = await limiter.allow("knot:redirect:user-a", rule)
            assert d.allowed is True
        # 11번째는 denied
        d = await limiter.allow("knot:redirect:user-a", rule)
        assert d.allowed is False
        assert d.remaining == 0
        assert d.retry_after > 0


@pytest.mark.asyncio
async def test_refill_after_time_advance(limiter, rule):
    with freeze_time("2026-05-24 12:00:00") as ft:
        # 버킷 비우기
        for _ in range(10):
            await limiter.allow("knot:redirect:user-b", rule)
        denied = await limiter.allow("knot:redirect:user-b", rule)
        assert denied.allowed is False

        # 1초 후 → 5 토큰 회복
        ft.tick(1.0)
        d = await limiter.allow("knot:redirect:user-b", rule)
        assert d.allowed is True
        # 1초에 5 회복했고 1개 차감 → remaining ≈ 4
        assert d.remaining in (3, 4)


@pytest.mark.asyncio
async def test_overfill_capped_at_capacity(limiter, rule):
    with freeze_time("2026-05-24 12:00:00") as ft:
        # 1회 호출 (last_refill 기록)
        await limiter.allow("knot:redirect:user-c", rule)
        # 1시간 후 (이론상 18000 토큰 회복) → capacity로 capped
        ft.tick(3600)
        d = await limiter.allow("knot:redirect:user-c", rule)
        assert d.allowed is True
        assert d.remaining == 9  # capacity=10, 1개 차감


@pytest.mark.asyncio
async def test_identities_have_separate_buckets(limiter, rule):
    with freeze_time("2026-05-24 12:00:00"):
        for _ in range(10):
            await limiter.allow("knot:redirect:user-x", rule)
        # user-x는 비었지만 user-y는 풀
        d = await limiter.allow("knot:redirect:user-y", rule)
        assert d.allowed is True
        assert d.remaining == 9
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd experiments/knot && uv run pytest tests/unit/test_token_bucket.py -v`
Expected: `ModuleNotFoundError: No module named 'app.limiter.token_bucket'`

- [ ] **Step 3: `token_bucket.py` 구현**

```python
# experiments/knot/app/limiter/token_bucket.py
from __future__ import annotations

from pathlib import Path

from app.limiter.base import Decision, Rule
from app.redis_client import get_redis

_SCRIPT_PATH = Path(__file__).parent / "scripts" / "token_bucket.lua"
_SCRIPT_SRC = _SCRIPT_PATH.read_text()

_UNIT_SECONDS = {"second": 1, "minute": 60, "hour": 3600}


class TokenBucket:
    def __init__(self) -> None:
        self._script_src = _SCRIPT_SRC
        self._script = None  # lazy register on first allow()

    async def allow(self, key: str, rule: Rule) -> Decision:
        if self._script is None:
            self._script = get_redis().register_script(self._script_src)

        capacity = rule.burst or rule.requests_per_unit
        rate = rule.requests_per_unit / _UNIT_SECONDS[rule.unit]
        bucket_key = key.replace("knot:", "knot:bucket:", 1)

        result = await self._script(keys=[bucket_key], args=[capacity, rate, 1])
        allowed, remaining, retry_ms = result

        return Decision(
            allowed=bool(int(allowed)),
            limit=capacity,
            remaining=int(remaining),
            retry_after=int(retry_ms) / 1000.0,
        )
```

- [ ] **Step 4: 테스트 실행, 통과 확인**

Run: `cd experiments/knot && uv run pytest tests/unit/test_token_bucket.py -v`
Expected: 5 passed.

**문제 발생 가능성**: `freezegun`이 fakeredis 내부 `redis.call('TIME')`을 잡지 못할 수 있음. 잡지 못하면 시간 ticking이 알고리즘에 반영 안 되어 `test_refill_after_time_advance`가 실패.

**대안 (실패 시)**: fakeredis의 `TIME` 명령이 실제 system time을 호출하는지 확인. 안 되면:
- (a) `freezegun` 외에 `monkeypatch.setattr("time.time", ...)` 병행
- (b) fakeredis가 `TIME`을 어떻게 구현하는지 봐서 monkeypatch
- (c) integration 테스트로 시간 검증을 옮기고 unit은 frozen time 가정 없이 호출 횟수만 검증

- [ ] **Step 5: 커밋**

```bash
git add experiments/knot/app/limiter/token_bucket.py experiments/knot/tests/unit/test_token_bucket.py
git commit -m "experiment: knot cycle 1 - TokenBucket limiter + unit tests (fakeredis + freezegun)"
```

---

## Task 3: Registry 등록 + rules.yaml 변경 (e2e 검증)

**Files:**
- Modify: `experiments/knot/app/limiter/registry.py`
- Modify: `experiments/knot/rules.yaml`
- Modify: `experiments/knot/tests/integration/test_middleware_e2e.py` (기존 테스트 기대값 갱신)

- [ ] **Step 1: registry에 1줄 추가**

```python
# experiments/knot/app/limiter/registry.py
from app.limiter.always_allow import AlwaysAllow
from app.limiter.base import Limiter
from app.limiter.token_bucket import TokenBucket

_LIMITERS: dict[str, Limiter] = {
    "always_allow": AlwaysAllow(),
    "token_bucket": TokenBucket(),
}


def get_limiter(algorithm: str) -> Limiter:
    try:
        return _LIMITERS[algorithm]
    except KeyError as e:
        raise KeyError(f"unknown algorithm: {algorithm}") from e
```

- [ ] **Step 2: rules.yaml 변경 — redirect만**

```yaml
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
      algorithm: token_bucket
      unit: second
      requests_per_unit: 50
      burst: 100
```

- [ ] **Step 3: 기존 e2e 테스트 기대값 갱신**

`tests/integration/test_middleware_e2e.py`의 `test_redirect_returns_302_with_rate_limit_headers`:

old (always_allow 기대):
```python
assert response.headers["x-ratelimit-limit"] == "50"
```

new (token_bucket 기대: limit = burst = 100):
```python
assert response.headers["x-ratelimit-limit"] == "100"
# remaining은 99 (cost=1 차감)
assert response.headers["x-ratelimit-remaining"] == "99"
```

- [ ] **Step 4: 전체 테스트 실행 (실 Redis 필요)**

Run: `docker compose up -d redis && cd experiments/knot && REDIS_AVAILABLE=1 uv run pytest -v`
Expected: 모든 테스트 통과 (cycle 0의 10개 + cycle 1의 5개 unit = 15개 이상).

- [ ] **Step 5: 커밋**

```bash
git add experiments/knot/app/limiter/registry.py experiments/knot/rules.yaml experiments/knot/tests/integration/test_middleware_e2e.py
git commit -m "experiment: knot cycle 1 - registry에 token_bucket 등록, redirect 정책 전환"
```

---

## Task 4: 통합 테스트 (실제 Redis + race demo)

**Files:**
- Create: `experiments/knot/tests/integration/test_token_bucket_redis.py`

- [ ] **Step 1: 통합 테스트 작성**

```python
# experiments/knot/tests/integration/test_token_bucket_redis.py
import asyncio

import pytest


@pytest.mark.asyncio
async def test_redirect_burst_absorption(client):
    """Burst capacity=100까지 통과, 그 다음은 429."""
    # 단축 코드 생성 (rate limit 영향 없도록 X-API-Key로 식별 분리)
    create = await client.post(
        "/shorten",
        json={"url": "https://example.com"},
        headers={"x-api-key": "burst-test"},
    )
    code = create.json()["code"]

    # 순차 100회 — capacity 안에 들어와야 함
    statuses = []
    for _ in range(105):
        r = await client.get(f"/{code}", follow_redirects=False)
        statuses.append(r.status_code)

    passed = sum(1 for s in statuses if s == 302)
    denied = sum(1 for s in statuses if s == 429)
    # rate가 50/s라 순차 호출 중 일부 refill 발생 → 최소 100개는 통과
    assert passed >= 100
    assert denied <= 5


@pytest.mark.asyncio
async def test_race_condition_atomic(client):
    """동시 200 요청에 정확히 capacity 개수만 통과 (Lua atomicity 증명)."""
    create = await client.post(
        "/shorten",
        json={"url": "https://example.com"},
        headers={"x-api-key": "race-test"},
    )
    code = create.json()["code"]

    # capacity=100, rate=50/s. 동시 200 요청 → 100개만 통과해야 함
    async def hit():
        r = await client.get(f"/{code}", follow_redirects=False)
        return r.status_code

    results = await asyncio.gather(*[hit() for _ in range(200)])
    passed = sum(1 for s in results if s == 302)
    denied = sum(1 for s in results if s == 429)

    # asyncio.gather는 사실상 동시 — 거의 모든 요청이 refill 전에 도착
    # 100±5 통과를 기대 (Lua atomic이면 정확히 100, 비atomic이면 200개 모두 통과)
    assert 95 <= passed <= 110, f"passed={passed} — atomic 위반 가능성"
    assert passed + denied == 200


@pytest.mark.asyncio
async def test_identity_isolation(client):
    """다른 API key는 별도 bucket."""
    create = await client.post("/shorten", json={"url": "https://example.com"})
    code = create.json()["code"]

    # user-a로 capacity 소진
    for _ in range(100):
        await client.get(f"/{code}", headers={"x-api-key": "user-a"}, follow_redirects=False)

    # user-b는 fresh
    r = await client.get(f"/{code}", headers={"x-api-key": "user-b"}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["x-ratelimit-remaining"] == "99"
```

- [ ] **Step 2: 실행**

Run: `docker compose up -d redis && REDIS_AVAILABLE=1 uv run pytest tests/integration/test_token_bucket_redis.py -v`
Expected: 3 passed.

**race demo가 실패하면 (`passed > 110`)**: Lua가 atomic하게 안 돌고 있다는 신호. 디버깅 우선순위 → 학습 가치 큼. 원인 후보:
- `register_script`가 매 호출 새로 SHA 등록 (캐시 안 됨)
- `redis.call('TIME')`이 매 호출 다른 인스턴스에서 다른 결과
- redis-py async pipeline이 Lua를 분해 (예상 안 됨)

- [ ] **Step 3: 커밋**

```bash
git add experiments/knot/tests/integration/test_token_bucket_redis.py
git commit -m "experiment: knot cycle 1 - token bucket 통합 테스트 + race demo (Lua atomicity 증명)"
```

---

## Task 5: Report generator 골격 (`scripts/report.py`)

**Files:**
- Create: `experiments/knot/scripts/__init__.py`
- Create: `experiments/knot/scripts/report.py`

- [ ] **Step 1: 디렉터리**

```bash
mkdir -p experiments/knot/scripts experiments/knot/reports
touch experiments/knot/scripts/__init__.py
```

- [ ] **Step 2: `report.py` 작성** (알고리즘 무관)

```python
# experiments/knot/scripts/report.py
"""k6 JSON 결과를 받아 마크다운 리포트 + matplotlib PNG 차트 생성.

사용:
    uv run python scripts/report.py \
        --k6-json out/token_bucket.json \
        --algorithm token_bucket \
        --output reports/token_bucket.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


def load_k6_json(path: Path) -> pd.DataFrame:
    """k6 --out json은 NDJSON 형식 (한 줄에 한 metric point)."""
    rows = []
    with path.open() as f:
        for line in f:
            obj = json.loads(line)
            if obj.get("type") == "Point":
                rows.append({
                    "metric": obj["metric"],
                    "time": pd.to_datetime(obj["data"]["time"]),
                    "value": obj["data"]["value"],
                    "scenario": obj["data"].get("tags", {}).get("scenario", "unknown"),
                    "status": obj["data"].get("tags", {}).get("status", ""),
                })
    return pd.DataFrame(rows)


def chart_pass_deny_timeseries(df: pd.DataFrame, out: Path) -> None:
    """시간버킷별 통과(2xx,3xx)·거부(429) 카운트 stacked bar."""
    http_reqs = df[df["metric"] == "http_reqs"].copy()
    http_reqs["bucket"] = http_reqs["time"].dt.floor("S")
    http_reqs["result"] = http_reqs["status"].apply(
        lambda s: "denied" if s == "429" else "passed"
    )
    pivot = http_reqs.groupby(["bucket", "result"]).size().unstack(fill_value=0)
    if "passed" not in pivot.columns:
        pivot["passed"] = 0
    if "denied" not in pivot.columns:
        pivot["denied"] = 0

    ax = pivot[["passed", "denied"]].plot(
        kind="bar", stacked=True, color=["#4caf50", "#f44336"], figsize=(12, 4)
    )
    ax.set_title("Requests over time (passed vs denied)")
    ax.set_xlabel("time (second)")
    ax.set_ylabel("requests")
    plt.tight_layout()
    plt.savefig(out, dpi=120)
    plt.close()


def chart_scenario_summary(df: pd.DataFrame) -> str:
    """시나리오별 통과율·p50/p95 지연 표 (마크다운)."""
    http_reqs = df[df["metric"] == "http_reqs"]
    summary = http_reqs.groupby("scenario").agg(
        total=("value", "count"),
        denied=("status", lambda s: (s == "429").sum()),
    )
    summary["pass_rate"] = (1 - summary["denied"] / summary["total"]) * 100

    duration = df[df["metric"] == "http_req_duration"].groupby("scenario")["value"]
    summary["p50_ms"] = duration.quantile(0.50).round(1)
    summary["p95_ms"] = duration.quantile(0.95).round(1)

    return summary.to_markdown()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--k6-json", required=True, type=Path)
    p.add_argument("--algorithm", required=True)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()

    df = load_k6_json(args.k6_json)
    if df.empty:
        raise SystemExit(f"no data in {args.k6_json}")

    chart_dir = args.output.parent
    chart_dir.mkdir(parents=True, exist_ok=True)
    timeseries_png = chart_dir / f"{args.algorithm}_timeseries.png"
    chart_pass_deny_timeseries(df, timeseries_png)

    summary_table = chart_scenario_summary(df)

    md = f"""# {args.algorithm} — 부하 시험 결과

> k6 시나리오 3종(burst·ramp·cycle) 결과. 알고리즘 비교는 cycle 2 이후 cross-link.

## 시간축별 통과/거부

![timeseries]({timeseries_png.name})

## 시나리오별 요약

{summary_table}

---

생성: `uv run python scripts/report.py --k6-json {args.k6_json} --algorithm {args.algorithm} --output {args.output}`
"""
    args.output.write_text(md)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: import 검증** (실행 안 함, 인자 부족하지만 import만 확인)

Run: `cd experiments/knot && uv run python -c "import scripts.report; print('ok')"`
Expected: `ok`

- [ ] **Step 4: 커밋**

```bash
git add experiments/knot/scripts experiments/knot/reports/.gitkeep 2>/dev/null
mkdir -p experiments/knot/reports && touch experiments/knot/reports/.gitkeep
git add experiments/knot/scripts experiments/knot/reports/.gitkeep
git commit -m "experiment: knot cycle 1 - scripts/report.py (k6 JSON → matplotlib → md)"
```

---

## Task 6: k6 시나리오

**Files:**
- Create: `experiments/knot/load/token_bucket.k6.js`

- [ ] **Step 1: 디렉터리**

```bash
mkdir -p experiments/knot/load
```

- [ ] **Step 2: k6 스크립트 작성**

```javascript
// experiments/knot/load/token_bucket.k6.js
import http from 'k6/http';
import { check } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://host.docker.internal:8000';
const CODE = __ENV.CODE;  // 사전 단축 코드 (외부에서 주입)

export const options = {
  scenarios: {
    burst: {
      executor: 'per-vu-iterations',
      vus: 200,
      iterations: 1,
      maxDuration: '5s',
      startTime: '0s',
      tags: { scenario: 'burst' },
    },
    ramp: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      stages: [
        { duration: '60s', target: 100 },
      ],
      preAllocatedVUs: 50,
      maxVUs: 200,
      timeUnit: '1s',
      startTime: '10s',
      tags: { scenario: 'ramp' },
    },
    steady_burst_cycle: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      stages: [
        { duration: '1s', target: 100 }, { duration: '5s', target: 0 },
        { duration: '1s', target: 100 }, { duration: '5s', target: 0 },
        { duration: '1s', target: 100 }, { duration: '5s', target: 0 },
      ],
      preAllocatedVUs: 100,
      maxVUs: 200,
      timeUnit: '1s',
      startTime: '80s',
      tags: { scenario: 'steady_burst_cycle' },
    },
  },
  thresholds: {
    'http_reqs{status:429}': ['count>0'],  // 거부가 일어나야 token bucket 검증 의미
  },
};

export default function () {
  const res = http.get(`${BASE_URL}/${CODE}`, { redirects: 0 });
  check(res, {
    'status is 302 or 429': (r) => r.status === 302 || r.status === 429,
  });
}
```

- [ ] **Step 3: 실행 가능성 점검 (실행 X)**

Run: `cat experiments/knot/load/token_bucket.k6.js | head -5`
Expected: 파일 내용 표시. (k6 실제 실행은 Task 7)

- [ ] **Step 4: 커밋**

```bash
git add experiments/knot/load/token_bucket.k6.js
git commit -m "experiment: knot cycle 1 - k6 burst/ramp/cycle 시나리오"
```

---

## Task 7: k6 실행 + reports/token_bucket.md 생성

**Files:**
- Create (생성됨): `experiments/knot/reports/token_bucket.md`
- Create (생성됨): `experiments/knot/reports/token_bucket_timeseries.png`

- [ ] **Step 1: 앱 실행 (별도 터미널)**

```bash
cd experiments/knot
docker compose up -d redis
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- [ ] **Step 2: 단축 코드 1개 생성**

```bash
CODE=$(curl -s -X POST http://localhost:8000/shorten \
  -H "content-type: application/json" \
  -H "x-api-key: load-test" \
  -d '{"url": "https://example.com"}' | python -c "import sys, json; print(json.load(sys.stdin)['code'])")
echo "CODE=$CODE"
```

- [ ] **Step 3: k6 실행 (Docker)**

```bash
mkdir -p experiments/knot/out
docker run --rm -i \
  -v $(pwd)/experiments/knot:/work -w /work \
  -e CODE=$CODE \
  grafana/k6 run \
  --out json=out/token_bucket.json \
  load/token_bucket.k6.js
```

Expected: 약 95초 후 통계 출력. `http_reqs{status:429}` count > 0 확인.

- [ ] **Step 4: 리포트 생성**

```bash
cd experiments/knot
uv run python scripts/report.py \
  --k6-json out/token_bucket.json \
  --algorithm token_bucket \
  --output reports/token_bucket.md
```

Expected: `wrote reports/token_bucket.md`, `reports/token_bucket_timeseries.png` 생성.

- [ ] **Step 5: 결과 확인**

```bash
cat experiments/knot/reports/token_bucket.md
```

차트가 token bucket의 시그니처(burst 흡수·refill 회복)를 보여주는지 눈으로 확인. 그래프가 이상하면 시나리오·rule 파라미터 재조정.

- [ ] **Step 6: 앱 종료 + 커밋**

앱 터미널: Ctrl+C.

```bash
git add experiments/knot/reports/token_bucket.md experiments/knot/reports/token_bucket_timeseries.png
git commit -m "experiment: knot cycle 1 - k6 부하 측정 + reports/token_bucket.md 생성"
```

**`out/` 디렉터리는 gitignore** — 큰 JSON 파일은 commit 안 함. 필요 시 `experiments/knot/.gitignore` 추가:

```bash
echo "out/" >> experiments/knot/.gitignore
git add experiments/knot/.gitignore
git commit -m "chore: knot/out/ gitignore (k6 raw output)"
```

---

## Task 8: wiki/projects/knot.md cycle 1 섹션 append

**Files:**
- Modify: `wiki/projects/knot.md`

- [ ] **Step 1: cycle 1 섹션 추가**

`wiki/projects/knot.md`의 끝(`## Cycle 1 — Token Bucket (예정)` 블록 위치)에 실제 내용 채워넣기. "예정" 표시를 지우고 다음 구조로 작성:

````markdown
## Cycle 1 — Token Bucket

**목표**: [[token-bucket-algorithm]]을 plug-in으로 끼우고 k6 부하 실측으로 ch04 비교표의 "버스트 허용" 시그니처 시각화.

**커밋 (8개)**:
- Lua script + dev deps
- TokenBucket limiter + unit (fakeredis + freezegun)
- Registry 등록 + rules.yaml 전환 + e2e 갱신
- 통합 테스트 (race demo 포함)
- scripts/report.py 골격 (알고리즘 무관)
- k6 burst/ramp/cycle 시나리오
- 실행 + reports/token_bucket.md
- chore: out/ gitignore

### Task 1 — Lua script + 의존성 추가

(왜 별도 .lua 파일인지, freezegun/pandas/matplotlib을 왜 dev로만 추가했는지)

### Task 2 — TokenBucket 클래스 (TDD)

(register_script 패턴, fakeredis vs 실 Redis 분리 이유, freezegun이 fakeredis TIME과 맞물리는 방식)

### Task 3 — Registry 등록 + rules.yaml 전환

(사이클별 변경 1개 원칙 — shorten은 cycle 4까지 손대지 않는 이유)

### Task 4 — Race Condition 데모

(asyncio.gather 200 → 정확히 100 통과의 의미. ch04 §"race condition"이 코드로 증명되는 지점)

### Task 5 — Report generator

(알고리즘 무관 스크립트로 짠 이유 — cycle 2~5의 재사용. k6 NDJSON 처리 패턴)

### Task 6 — k6 시나리오 3종

(burst·ramp·cycle이 token bucket의 어떤 특성을 각각 격리 시연하는지)

### Task 7 — 실측 + 리포트

(차트에서 본 것 — burst 흡수, refill 곡선, 거부 패턴. ch04 비교표의 "버스트 허용" 셀이 실제로 무엇을 의미하는지)

### Cycle 1 회고

- [token-bucket-algorithm]] 페이지의 의사코드가 코드로 옮겨졌을 때 마주친 함정 (freezegun + fakeredis TIME 등)
- Lua atomicity의 실증 (race demo 결과)
- 다음 사이클 ([[leaking-bucket-algorithm]])과의 차이가 무엇이 될지

**결정 이력**: spec `docs/specs/2026-05-24-knot-cycle-1-token-bucket-design.md` §7 참조.
````

위 본문의 괄호 친 항목은 **실측 결과를 본 후 채워야** 하는 부분. T7의 차트와 race demo 결과를 보고 사실대로 기록.

- [ ] **Step 2: 커밋**

```bash
git add wiki/projects/knot.md
git commit -m "docs: wiki/projects/knot.md - cycle 1 (token bucket) 학습 노트 append"
```

---

## Task 9: spec status + log.md + push

**Files:**
- Modify: `docs/specs/2026-05-24-rate-limiter-design.md` (§7 cycle 1 status)
- Modify: `log.md`

- [ ] **Step 1: 상위 spec status 업데이트**

`docs/specs/2026-05-24-rate-limiter-design.md` §7 표:

old:
```
| 1 | Token bucket + k6 burst 시나리오 + report | token bucket, 버스트 허용 | todo |
```

new:
```
| 1 | Token bucket + k6 burst 시나리오 + report | token bucket, 버스트 허용 | done (2026-05-24) |
```

- [ ] **Step 2: log.md append**

```markdown

## [2026-05-24] experiment | knot cycle 1: Token Bucket

[[token-bucket-algorithm]] plug-in 완성 + k6 부하 실측 + matplotlib 리포트 도구 chain 1회 셋업. Lua script + `redis.call('TIME')`로 atomicity 보장, asyncio.gather 200 동시 요청 race demo로 직접 증명. cycle 2~5는 알고리즘 모듈만 추가하면 같은 도구 chain 재사용.

- `experiments/knot/app/limiter/token_bucket.py`, `scripts/token_bucket.lua` 신규
- `experiments/knot/scripts/report.py` 신규 (알고리즘 무관)
- `experiments/knot/load/token_bucket.k6.js`, `reports/token_bucket.md` 신규
- `wiki/projects/knot.md` cycle 1 섹션 append
- 결정 이력: spec `docs/specs/2026-05-24-knot-cycle-1-token-bucket-design.md` §7
```

- [ ] **Step 3: stub 점검**

```bash
git status --short
find . -maxdepth 3 -name "*.md" -size 0 -not -path "./.git/*"
```

- [ ] **Step 4: 최종 커밋 + push**

```bash
git add docs/specs/2026-05-24-rate-limiter-design.md log.md
git commit -m "experiment: knot cycle 1 완료 - spec status + log"
git push -u origin experiment/knot-cycle-1
```

- [ ] **Step 5: PR 생성**

```bash
gh pr create --base main --head experiment/knot-cycle-1 \
  --title "experiment: knot cycle 1 (Token Bucket)" \
  --body "..."
```

PR body는 cycle 0 PR 형식 참고. 핵심: 다룬 ch04 개념, race demo 결과, 다음 사이클 예고.

---

## 검증 체크리스트 (cycle 1 완료 기준)

- [ ] `uv run pytest -v` 전체 통과 (cycle 0 unit 6 + integration 4 + cycle 1 unit 5 + integration 3 = 18개)
- [ ] `docker compose up -d redis && curl -X POST localhost:8000/shorten ...` → 200
- [ ] 100회 `curl /{code}` 후 101번째 → 429 + `X-Ratelimit-Retry-After`
- [ ] Race demo: 200 동시 → 100±10 통과 (Lua atomic 증명)
- [ ] `reports/token_bucket.md` 생성, timeseries 차트가 burst 흡수·refill 시각화
- [ ] `wiki/projects/knot.md` cycle 1 섹션 완성 (실측 본 후 회고 채움)
- [ ] spec §7 cycle 1 status = `done (2026-05-24)`
- [ ] PR #N 생성 및 머지

## 다음 사이클

**Cycle 2 — Leaking Bucket**: 같은 plug-in 슬롯에 [[leaking-bucket-algorithm]] 추가. k6 시나리오는 같은 3종을 재사용해 token bucket과 비교 차트. `scripts/report.py`가 overlay 기능 필요해질 수 있음 — 그때 확장.
