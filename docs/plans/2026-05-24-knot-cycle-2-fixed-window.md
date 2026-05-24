# knot Cycle 2 — Fixed Window (Demo Lite) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** [[fixed-window-counter-algorithm]]을 knot에 구현하고 **윈도우 경계 burst 한계를 그래프로 시연**. knot 엔드포인트 정책은 변경 없음 (demo lite).

**Architecture:** cycle 1과 동일한 plug-in 구조 — Lua script + INCR + TIME으로 atomic 윈도우 카운터. 단, 통합 테스트 없음(엔드포인트 미사용), k6 시나리오 1개(boundary burst), 짧은 wiki 섹션.

**Spec:** `docs/specs/2026-05-24-knot-cycle-2-fixed-window-design.md` (결정 이력 10개).

**Scope (4 task)**:
1. Lua + FixedWindow + unit tests (TDD)
2. Registry 1줄 등록
3. boundary burst demo — 임시 rules.yaml + k6 + report
4. wiki cycle 2 섹션 + spec status + log + push + PR

---

## File Structure

```
신규: app/limiter/scripts/fixed_window.lua, app/limiter/fixed_window.py
신규: tests/unit/test_fixed_window.py
신규: load/fixed_window_boundary.k6.js
신규: reports/fixed_window.md (+ PNG, T3 생성)
변경: app/limiter/registry.py (1줄)
변경: .gitignore (tmp_rules.yaml)
```

---

## Task 1: Lua + FixedWindow + unit (TDD)

**Files:**
- Create: `experiments/knot/app/limiter/scripts/fixed_window.lua`
- Create: `experiments/knot/app/limiter/fixed_window.py`
- Test: `experiments/knot/tests/unit/test_fixed_window.py`

- [ ] **Step 1: Lua script 작성**

```lua
-- experiments/knot/app/limiter/scripts/fixed_window.lua
-- KEYS[1] = base key prefix (knot:fw:endpoint:identity)
-- ARGV[1] = limit (int), ARGV[2] = window_size_seconds (int)
-- returns: {allowed (0|1), limit, remaining, retry_after_ms, window_start}

local now_pair = redis.call('TIME')
local now = tonumber(now_pair[1])
local window_size = tonumber(ARGV[2])
local window_start = math.floor(now / window_size) * window_size

local key = KEYS[1] .. ':' .. window_start
local count = redis.call('INCR', key)

if count == 1 then
  redis.call('EXPIRE', key, window_size + 5)
end

local limit = tonumber(ARGV[1])
local allowed = 0
local remaining = 0
local retry_after_ms = 0

if count <= limit then
  allowed = 1
  remaining = limit - count
else
  remaining = 0
  retry_after_ms = (window_start + window_size - now) * 1000
end

return {allowed, limit, remaining, retry_after_ms, window_start}
```

- [ ] **Step 2: 실패하는 unit 테스트 작성** (3개)

```python
# experiments/knot/tests/unit/test_fixed_window.py
from __future__ import annotations

import pytest
from freezegun import freeze_time

from app.limiter.base import Rule


@pytest.fixture
def rule():
    # 5 req per 10 seconds
    return Rule(algorithm="fixed_window", unit="second", requests_per_unit=5)


@pytest.fixture
async def limiter(monkeypatch):
    import fakeredis.aioredis
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    import app.redis_client
    monkeypatch.setattr(app.redis_client, "_client", fake)
    from app.limiter.fixed_window import FixedWindow
    return FixedWindow()


@pytest.mark.asyncio
async def test_basic_pass_then_deny(limiter, rule):
    """5번 통과 + 6번째 거부."""
    rule_per_min = Rule(algorithm="fixed_window", unit="minute", requests_per_unit=5)
    with freeze_time("2026-05-24 12:00:30"):
        for i in range(5):
            d = await limiter.allow("knot:test:user-a", rule_per_min)
            assert d.allowed is True, f"req {i+1} should pass"
            assert d.remaining == 4 - i
        # 6th
        d = await limiter.allow("knot:test:user-a", rule_per_min)
        assert d.allowed is False
        assert d.remaining == 0
        assert d.retry_after > 0


@pytest.mark.asyncio
async def test_boundary_burst_demonstrates_2x(limiter, rule):
    """ch04 §"fixed window 한계": 윈도우 경계 전후로 5+5 = 10 통과 (의도 2x).

    분 단위 limit=5에서 1분의 마지막 1초에 5번 + 다음 분 첫 1초에 5번 → 2초간 10 통과.
    의도된 정책 (분당 5)의 2배가 단기적으로 통과되는 fixed window의 한계.
    """
    rule_per_min = Rule(algorithm="fixed_window", unit="minute", requests_per_unit=5)

    # 12:00:59 — 1분의 마지막 직전, 5개 burst
    with freeze_time("2026-05-24 12:00:59") as ft:
        for _ in range(5):
            d = await limiter.allow("knot:test:user-b", rule_per_min)
            assert d.allowed is True
        # 6번째는 deny (이 윈도우 한도 소진)
        d = await limiter.allow("knot:test:user-b", rule_per_min)
        assert d.allowed is False

        # 1초 흐름 → 다음 분(12:01:00)
        ft.tick(1.0)
        # 새 윈도우: 5개 더 통과
        for _ in range(5):
            d = await limiter.allow("knot:test:user-b", rule_per_min)
            assert d.allowed is True
        # 6번째 deny
        d = await limiter.allow("knot:test:user-b", rule_per_min)
        assert d.allowed is False

    # 결론: 12:00:59 ~ 12:01:00 (2초 구간)에 10 통과 — 의도(분당 5)의 2배


@pytest.mark.asyncio
async def test_window_isolation_no_carryover(limiter, rule):
    """한 윈도우 소진 후 다음 윈도우는 fresh — carryover 없음."""
    rule_per_min = Rule(algorithm="fixed_window", unit="minute", requests_per_unit=5)
    with freeze_time("2026-05-24 12:00:00") as ft:
        for _ in range(5):
            await limiter.allow("knot:test:user-c", rule_per_min)
        # 다음 분으로
        ft.tick(60.0)
        d = await limiter.allow("knot:test:user-c", rule_per_min)
        assert d.allowed is True
        assert d.remaining == 4  # 5 - 1 (fresh window)
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd experiments/knot && uv run pytest tests/unit/test_fixed_window.py -v`
Expected: `ModuleNotFoundError: No module named 'app.limiter.fixed_window'`

- [ ] **Step 4: FixedWindow 구현**

```python
# experiments/knot/app/limiter/fixed_window.py
from __future__ import annotations

from pathlib import Path

from app.limiter.base import Decision, Rule
from app.redis_client import get_redis

_SCRIPT_PATH = Path(__file__).parent / "scripts" / "fixed_window.lua"
_SCRIPT_SRC = _SCRIPT_PATH.read_text()

_UNIT_SECONDS = {"second": 1, "minute": 60, "hour": 3600}


class FixedWindow:
    def __init__(self) -> None:
        self._script = None
        self._script_client = None

    async def allow(self, key: str, rule: Rule) -> Decision:
        client = get_redis()
        if self._script is None or self._script_client is not client:
            self._script = client.register_script(_SCRIPT_SRC)
            self._script_client = client

        window_size = _UNIT_SECONDS[rule.unit]
        base_key = key.replace("knot:", "knot:fw:", 1)

        result = await self._script(
            keys=[base_key],
            args=[rule.requests_per_unit, window_size],
        )
        allowed, limit, remaining, retry_ms, _window_start = result

        return Decision(
            allowed=bool(int(allowed)),
            limit=int(limit),
            remaining=int(remaining),
            retry_after=int(retry_ms) / 1000.0,
        )
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd experiments/knot && uv run pytest tests/unit/test_fixed_window.py -v`
Expected: 3 passed.

- [ ] **Step 6: 커밋**

```bash
git add experiments/knot/app/limiter/scripts/fixed_window.lua experiments/knot/app/limiter/fixed_window.py experiments/knot/tests/unit/test_fixed_window.py
git commit -m "experiment: knot cycle 2 - FixedWindow limiter + Lua + unit (경계 burst 단위 시연 포함)"
```

---

## Task 2: Registry 등록

**Files:**
- Modify: `experiments/knot/app/limiter/registry.py`

- [ ] **Step 1: 1줄 추가**

```python
# experiments/knot/app/limiter/registry.py
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
```

- [ ] **Step 2: 기존 테스트 전체 통과 확인**

Run: `docker compose up -d redis && cd experiments/knot && REDIS_AVAILABLE=1 uv run pytest -v`
Expected: 21 passed (cycle 0: 10, cycle 1: 8, cycle 2: 3).

- [ ] **Step 3: 커밋**

```bash
git add experiments/knot/app/limiter/registry.py
git commit -m "experiment: knot cycle 2 - registry에 fixed_window 등록"
```

---

## Task 3: Boundary burst demo (k6 + report) — **사이클의 핵심**

이 task가 cycle 2의 학습 목표. **그래프에서 fixed window의 경계 burst를 직접 보여줘야** 함.

**Files:**
- Create: `experiments/knot/load/fixed_window_boundary.k6.js`
- Create: `experiments/knot/reports/fixed_window.md` (생성됨, + PNG)
- Modify: `experiments/knot/.gitignore` (tmp_rules.yaml 추가)

### 시각 동기화 회피 전략

`limit=100/minute`로 시연하려면 시각이 정확히 분 경계에 맞춰야 함 — 번잡. 대신 **`window=10초`로 short window 사용**:

- limit=100/`window=10초`
- 시각 무관: 0~10초 100통과, 10~12초 새 윈도우 100통과 = 12초 동안 200 통과
- 그래프: 0초 burst spike → 10초 burst spike, 사이는 거부

(unit "second"가 우리 `_UNIT_SECONDS` 매핑에 있으므로 사용 가능. 단 한 unit이 곧 window는 아니므로 spec 약간 확장: `unit: second` + `requests_per_unit: 100` = 100/초가 됨. demo에선 short window를 `unit: minute` + `requests_per_unit: 100`로 두고 시각 동기화. 또는 unit 값을 임의 추가해도 됨.)

**가장 단순한 접근**: `unit: minute`, `requests_per_unit: 100`. 시연 시점을 분 경계 직전(~xx:xx:55)부터 시작해 약 12초 돌림. 분 경계가 자연스레 발생.

- [ ] **Step 1: k6 시나리오**

```javascript
// experiments/knot/load/fixed_window_boundary.k6.js
// 시나리오: 12초간 200rps 지속. 분 경계가 그 중간에 떨어지면 통과·거부 패턴이
// "burst pass → all deny → burst pass" 형태로 차트에 박힘.

import http from 'k6/http';
import { check } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://host.docker.internal:8001';
const CODE = __ENV.CODE;

export const options = {
  scenarios: {
    boundary_burst: {
      executor: 'constant-arrival-rate',
      rate: 200,            // 200 req/s
      timeUnit: '1s',
      duration: '12s',
      preAllocatedVUs: 100,
      maxVUs: 300,
      tags: { scenario: 'boundary_burst' },
    },
  },
};

export default function () {
  const res = http.get(`${BASE_URL}/${CODE}`, { redirects: 0 });
  check(res, { 'status is 302 or 429': (r) => r.status === 302 || r.status === 429 });
}
```

- [ ] **Step 2: 임시 rules.yaml + .gitignore**

```bash
# tmp_rules.yaml 작성 (demo 중에만 사용)
cat > experiments/knot/tmp_rules.yaml <<'EOF'
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
      algorithm: fixed_window
      unit: minute
      requests_per_unit: 100
EOF

echo "tmp_rules.yaml" >> experiments/knot/.gitignore
```

**중요**: `app/main.py`가 `rules.yaml` 경로를 하드코딩하고 있을 수 있음. 환경변수 override 지원하는지 확인:

```bash
grep -n "rules.yaml\|RULES_PATH" experiments/knot/app/main.py
```

미지원이면 `app/main.py` 1줄 수정:

```python
# old: RULES_PATH = Path(__file__).parent.parent / "rules.yaml"
RULES_PATH = Path(os.environ.get("KNOT_RULES_PATH", Path(__file__).parent.parent / "rules.yaml"))
```

이 수정은 영구적으로 유용 (테스트·demo override 가능). cycle 4 핫리로드에서도 활용.

- [ ] **Step 3: app 실행 (background) + demo 시각 동기화**

```bash
cd /Users/fetching/study/system-design/experiments/knot
docker compose up -d redis
docker compose exec -T redis redis-cli FLUSHALL

# app background
KNOT_RULES_PATH=$(pwd)/tmp_rules.yaml uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 &
APP_PID=$!
sleep 3

curl -sf http://localhost:8001/healthz | head -1

# 단축 코드
CODE=$(curl -s -X POST http://localhost:8001/shorten \
  -H "content-type: application/json" \
  -H "x-api-key: fw-demo" \
  -d '{"url": "https://example.com"}' | python3 -c "import sys, json; print(json.load(sys.stdin)['code'])")

# 분 경계가 시연 구간 중간에 떨어지도록 — 현재 분의 53초까지 대기
TARGET_SEC=53
while [ $(date +%S) -ne $TARGET_SEC ]; do sleep 0.2; done

# k6 12초 실행 (53s~65s 동안 분 경계 60s 통과)
mkdir -p out
docker run --rm -i \
  -v $(pwd):/work -w /work \
  -e CODE=$CODE \
  -e BASE_URL=http://host.docker.internal:8001 \
  grafana/k6 run \
  --out json=out/fixed_window.json \
  load/fixed_window_boundary.k6.js

# 앱 종료
kill $APP_PID
rm -f tmp_rules.yaml
```

**Expected**: k6 summary에서 `http_reqs{status:429}` count > 0. 12초간 약 200×12=2400 요청 중 약 200(=2 윈도우 × 100 limit) 통과 + 약 2200 거부. **차트에서 burst 통과가 시작 직후와 분 경계 직후 두 번 보여야 함**.

- [ ] **Step 4: 리포트 생성**

```bash
cd experiments/knot
uv run python scripts/report.py \
  --k6-json out/fixed_window.json \
  --algorithm fixed_window \
  --output reports/fixed_window.md
```

- [ ] **Step 5: 리포트에 경계 burst 해설 추가**

생성된 `reports/fixed_window.md`에 헤더 아래 짧은 해설 append. **자동 생성 후 사람이 한 단락만 손으로 추가**:

```markdown
## 경계 burst 시연 (ch04 §"fixed window 한계")

위 차트에서 두 번의 "통과 spike"를 확인할 수 있다 — 첫 spike는 k6 시작 직후
(현재 윈도우의 한도 100 흡수), 두 번째는 분 경계 직후 (새 윈도우 시작, 한도
다시 100 흡수). 두 spike 사이 약 5~7초는 첫 윈도우 한도 소진 상태라 모두 거부.

결과: 100req/minute의 의도된 정책이 분 경계를 끼는 2초 구간 동안 **최대 200 요청
통과**를 허용. 이게 ch04 §"알고리즘 비교"가 fixed window의 "정확도: 낮음
(경계 burst)"이라 적은 이유의 그래프 증명.

이 문제를 해결한 게 cycle 3의 [[sliding-window-log-algorithm]] — 임의 시점 기준
직전 N초 윈도우를 동적 계산해 경계 burst 제거.
```

- [ ] **Step 6: 커밋**

```bash
git add experiments/knot/load/fixed_window_boundary.k6.js \
        experiments/knot/reports/fixed_window.md \
        experiments/knot/reports/fixed_window_timeseries.png \
        experiments/knot/.gitignore

# main.py에 RULES_PATH env override 변경한 경우 함께
git add experiments/knot/app/main.py 2>/dev/null

git commit -m "experiment: knot cycle 2 - fixed_window boundary burst demo (k6 + report)"
```

---

## Task 4: wiki/projects/knot.md cycle 2 섹션 + spec status + log + push + PR

**Files:**
- Modify: `wiki/projects/knot.md`
- Modify: `docs/specs/2026-05-24-rate-limiter-design.md`
- Modify: `log.md`

- [ ] **Step 1: wiki cycle 2 섹션 append (짧게, demo lite 정신)**

```markdown

## Cycle 2 — Fixed Window Counter (demo lite)

**목표**: [[fixed-window-counter-algorithm]]의 "경계 burst" 한계를 그래프로 시연. knot 엔드포인트 정책 변경 없음 (demo 목적).

**산출**: 3 task (cycle 1의 1/3), 3개 unit + boundary burst k6 1개 + reports/fixed_window.md.

**Sub-spec**: `docs/specs/2026-05-24-knot-cycle-2-fixed-window-design.md` (결정 이력 10개).

### 학습 목표 — ch04가 글로만 설명한 "경계 burst" 시각화

ch04 §"알고리즘 비교": fixed window의 정확도 = **"낮음 (경계 burst)"**. 한 줄에 적혀 있던 이 한계가 무엇인지 그래프로 확인:

| 시각 | 요청 | 통과 |
|---|---|---|
| 12:00:53~12:00:59 | ~200req/s | 처음 100 통과, 나머지 거부 |
| 12:01:00~12:01:05 | ~200req/s | **새 윈도우 → 다시 100 통과**, 나머지 거부 |

결과: **약 2초 구간에 의도(분당 100)의 2배인 200 요청 통과**. 차트의 두 burst spike가 명확히 시각화.

### 구현 핵심 (cycle 1과의 차이)

- HASH 대신 string 카운터 (`INCR` + `EXPIRE`)
- TIME은 초 단위만 (윈도우 경계가 정수 초)
- `window_start = floor(now / window_size) * window_size` — Lua 핵심 한 줄
- Stale Script client binding 패턴은 cycle 1 학습 그대로 재사용

### 환경 변경 — `KNOT_RULES_PATH` env override 도입

demo 실행에 임시 rules.yaml(`tmp_rules.yaml`)이 필요해 `app/main.py`에 환경변수 override 추가. **cycle 4 핫리로드의 사전 셋업**이기도 함.

```python
RULES_PATH = Path(os.environ.get("KNOT_RULES_PATH", default_path))
```

### Cycle 2 회고 — demo lite의 가치

**전체 cycle의 1/3 시간**에 ch04 비교표의 한 셀("정확도: 낮음 (경계 burst)")의 의미가 명확히 박힘. full cycle(통합 테스트·다양한 k6 시나리오·풀 wiki)을 안 한 결정은 옳았음 — 학습 본질은 그래프 한 장.

cycle 3 ([[sliding-window-log-algorithm]] full)가 이 한계의 해결책. 두 알고리즘의 차이를 이번 그래프 + cycle 3 그래프 나란히 비교 가능.

**스킵된 알고리즘에 대한 회고**는 cycle 7에서 본격적으로 (왜 [[leaking-bucket-algorithm]] / [[sliding-window-counter-algorithm]] 안 했나, 실세계 어디서 쓰나).
```

- [ ] **Step 2: spec §7 status 갱신**

`docs/specs/2026-05-24-rate-limiter-design.md` §7 표:

old (cycle 2 행):
```
| 2 | **Fixed window demo lite** ... | fixed window + 경계 burst 한계 시연 | todo |
```

new:
```
| 2 | **Fixed window demo lite** ... | fixed window + 경계 burst 한계 시연 | done (2026-05-24) |
```

- [ ] **Step 3: log.md append**

```markdown

## [2026-05-24] experiment | knot cycle 2: Fixed Window (demo lite)

ch04 §"알고리즘 비교"의 fixed window "정확도: 낮음 (경계 burst)" 셀을 그래프로 시각화하는 demo. knot 엔드포인트 정책 변경 없음 — full cycle의 1/3 시간으로 학습 본질만 흡수. 분 경계 직전·직후 2초간 약 200req 통과(의도 100의 2배) 확인.

- `experiments/knot/app/limiter/fixed_window.py`, `scripts/fixed_window.lua` 신규
- `experiments/knot/load/fixed_window_boundary.k6.js`, `reports/fixed_window.md` 신규
- `app/main.py` — `KNOT_RULES_PATH` env override 추가 (cycle 4 핫리로드 사전 셋업)
- `wiki/projects/knot.md` cycle 2 짧은 섹션
- 결정 이력: spec `docs/specs/2026-05-24-knot-cycle-2-fixed-window-design.md` §6
```

- [ ] **Step 4: stub check + 커밋 + push + PR**

```bash
cd /Users/fetching/study/system-design
git status --short
find . -maxdepth 3 -name "*.md" -size 0 -not -path "./.git/*"

git add wiki/projects/knot.md docs/specs/2026-05-24-rate-limiter-design.md log.md
git commit -m "experiment: knot cycle 2 완료 — wiki + spec status + log"

git push -u origin experiment/knot-cycle-2

gh pr create --base main --head experiment/knot-cycle-2 \
  --title "experiment: knot cycle 2 (Fixed Window demo lite)" \
  --body "$(cat <<'EOF'
## Summary

ch04 §"알고리즘 비교"의 fixed window "정확도: 낮음 (경계 burst)" 셀을 그래프로 시각화하는 **demo lite** 사이클.

- 4 task (full cycle의 ~1/3 시간)
- 3 unit + 1 k6 boundary burst 시나리오 + 짧은 report + wiki 1개 섹션
- knot 엔드포인트 정책 변경 없음 (영구 등록은 registry에만)
- `app/main.py`에 `KNOT_RULES_PATH` env override 추가 (cycle 4 핫리로드 사전 셋업)

## 핵심 측정

분 경계 전후 2초간 약 200 요청 통과 — 의도된 정책(분당 100)의 2배. ch04 비교표 한 줄("정확도: 낮음")의 그래프 증명.

이 한계의 해결은 cycle 3 [[sliding-window-log-algorithm]] full에서.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## 검증 체크리스트

- [ ] `REDIS_AVAILABLE=1 uv run pytest -v` 21 passed (cycle 0: 10 + cycle 1: 8 + cycle 2 unit: 3)
- [ ] `reports/fixed_window.md`의 차트에서 분 경계 직후 두 번째 burst spike 시각화 확인
- [ ] `tmp_rules.yaml`은 gitignored, demo 후 삭제됨
- [ ] `app/main.py`의 KNOT_RULES_PATH env가 정상 동작 (기본 경로도 fallback)
- [ ] spec §7 cycle 2 status = `done (2026-05-24)`
- [ ] PR 생성

## 다음 사이클

**Cycle 3 — Sliding Window Log (full, for shorten)**: `shorten` 엔드포인트를 sliding_window_log로 전환. Lua + Redis sorted set + ZADD/ZREMRANGEBYSCORE/ZCARD 패턴. race demo는 atomic sorted set 조작이 진가 발휘. cycle 1의 8 task 형식 그대로.
