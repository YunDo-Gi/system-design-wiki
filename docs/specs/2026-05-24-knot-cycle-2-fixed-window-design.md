# knot Cycle 2 — Fixed Window Counter (Demo Lite) 설계

- **문서 종류**: Sub-spec (cycle 2 한정, demo lite)
- **상위 spec**: `docs/specs/2026-05-24-rate-limiter-design.md`
- **작성일**: 2026-05-24
- **관련 위키**: [[fixed-window-counter-algorithm]], [[ch04-rate-limiter]]
- **상태**: 작성 직후

## 0. 목적과 범위

[[fixed-window-counter-algorithm]]을 knot에 구현하되 **knot 엔드포인트는 변경하지 않는다**. 목적은 **ch04가 글로만 설명하는 "윈도우 경계 burst" 한계를 그래프로 직접 보여주는 demo**.

ch04는 fixed window의 트레이드오프를 비교표에 한 줄 적어놓음:

> "정확도: **낮음 (경계 burst)**"

이게 무엇인지 글로는 "윈도우 경계 직전·직후에 burst가 몰리면 단기적으로 2배 트래픽 통과"라고만 설명됨. **직접 그래프로 봐야** "아 이래서 sliding window가 나왔구나"가 박힘. cycle 2의 유일한 학습 목표.

### Lite 사이클의 의미 — cycle 1과의 차이

| | cycle 1 (token bucket) | cycle 2 (fixed window, **lite**) |
|---|---|---|
| 엔드포인트 변경 | redirect 정책 전환 | **변경 없음** (knot은 fixed window 안 씀) |
| Registry 등록 | 영구 | 등록은 하되 rules.yaml에 안 씀 |
| 통합 테스트 | race demo 포함 | **임시 rules.yaml override**로 demo 시나리오만 |
| k6 시나리오 | 3종 (burst·ramp·cycle) | **1종 (boundary burst)** |
| Report | 풀 차트 + 시나리오 표 | 한 차트(boundary burst 시각화) + 짧은 해설 |
| wiki 섹션 | 9개 task별 상세 | **1개 섹션 (경계 burst 시연·해설 위주)** |

3~4 task로 완료 목표. cycle 3(sliding window log full)을 위한 시간 확보.

## 1. Fixed Window Counter 알고리즘 (참조)

ch04 의사코드 (개념):

```
window_start = floor(now / window_size) * window_size
key = f"{endpoint}:{identity}:{window_start}"
count = INCR(key)
if count == 1: EXPIRE(key, window_size + buffer)
if count > limit: deny
else: allow
```

핵심 성질:

- **간단**: `INCR` + `EXPIRE` 두 명령 (Lua로 묶으면 atomic)
- **메모리 적음**: 키 1개/(엔드포인트 × 식별자 × 윈도우)
- **한계**: 윈도우는 epoch 시각 기준 정렬 (예: 매 분의 00초). 두 윈도우 경계에 burst가 몰리면 단기 2배 트래픽 통과

### 경계 burst 시연 시나리오

예: `limit = 5 req/minute`

```
시각:    12:00:59           12:01:00 (윈도우 전환)
요청:    [5 req in 1초]     [5 req in 1초]
window:  12:00:00~12:00:59  12:01:00~12:01:59
count:   1→5 (모두 통과)    1→5 (모두 통과)
결과:    2초 동안 10 req 통과 — 의도한 "분당 5"의 2배
```

ch04 비교표의 "낮음 (경계 burst)" 셀의 실체.

## 2. Storage layout

```
key:    knot:fw:{endpoint}:{identity}:{window_start_epoch}
type:   string (INCR로 카운터)
TTL:    window_size + 5초 buffer (전환 직후에도 잠시 살아있게)
```

token bucket의 HASH와 달리 string 카운터 — `INCR`이 단일 명령으로 atomic. 그러나 `INCR + EXPIRE`는 2명령이라 그 사이에 race 가능 → Lua로 묶음.

## 3. Atomic 연산 — Lua script

```lua
-- KEYS[1] = base key prefix (knot:fw:endpoint:identity)
-- ARGV[1] = limit (int)
-- ARGV[2] = window_size_seconds (int)
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

차이점 (cycle 1 token bucket과):

- TIME만 초 단위 정수 사용 (microsecond 무시) — 윈도우 경계가 정확히 정수 초로 떨어져야 직관적
- HASH 안 쓰고 단순 string 카운터 — `INCR`로 충분
- `retry_after_ms`는 다음 윈도우 시작 시각까지의 잔여 — token bucket(누적 토큰 회복 시간)과 의미 다름

## 4. Python 측 인터페이스

```python
# app/limiter/fixed_window.py
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

cycle 1 token bucket과 거의 동일 구조 — **stale client binding 패턴, lazy register, key 접두사 변환**. cycle 1의 학습이 그대로 재사용.

## 5. 테스트 전략

### Unit (`tests/unit/test_fixed_window.py`) — 3개

- `test_basic_pass_then_deny` — limit=5, 5번 통과 + 6번째 deny
- `test_boundary_burst_demonstrates_2x` — 윈도우 경계 전후로 5+5 = 10 통과 (한계 시연)
- `test_window_isolation` — 한 윈도우 소진 후 다음 윈도우 시작 시 carryover 없음

`freezegun`으로 윈도우 경계 시각 조작.

### Integration — **건너뜀**

knot 엔드포인트가 fixed_window를 안 쓰므로 e2e 통합 테스트 없음. demo k6 시나리오가 e2e 역할 (rules.yaml override로 실행).

### Load — k6 boundary burst 1개

`load/fixed_window_boundary.k6.js`:

```javascript
// 시나리오: 윈도우 경계 직전 5초간 100req/s, 직후 5초간 100req/s
// limit=100/minute로 설정 (rules.yaml override)
// 기대: 첫 5초 100통과, 다음 5초 또 100통과 → 10초간 200통과 (분당 한도 2배)
```

실행 절차 (T3에서 자동화):
1. 임시 rules.yaml 생성 (`tmp_rules.yaml`) — redirect를 fixed_window로 변경
2. `KNOT_RULES_PATH=tmp_rules.yaml uv run uvicorn ...`
3. 시각 동기화 (현재 분 59초 시작) — bash sleep + date 조작
4. k6 실행
5. 앱 종료

복잡 정도 봐서, 시각 동기화가 너무 까다로우면 **시각 무관 시연**으로 단순화: window=10초, 10초 동안 한도 100, 10~12초에 burst 1000 → 첫 10초에 100 통과, 10~12초에 새 윈도우 100 통과 = 12초 동안 200 통과.

### Report

`scripts/report.py` 재사용. 차트는 timeseries 1개 + 짧은 해설 마크다운.

## 6. 결정 이력 (Decision Log)

| # | 결정 | 선택 | 이유 |
|---|---|---|---|
| 1 | Cycle 2 형태 | demo lite (full cycle 아님) | knot 엔드포인트가 fixed_window 안 씀. boundary burst 시연만이 학습 가치 |
| 2 | 자료구조 | string 카운터 (`INCR`) | window별 카운터는 단일 정수면 충분. HASH 불필요 |
| 3 | TTL | `window_size + 5초 buffer` | 윈도우 전환 직후 잠시 살아있게 (디버깅·관측 용이) |
| 4 | atomic 연산 | Lua (INCR + EXPIRE 묶음) | INCR만 atomic이지만 EXPIRE는 별도 명령 → Lua로 묶어 race 없앰 |
| 5 | 시각 정수 | TIME의 초 단위만 사용 | 윈도우 경계가 정확히 정수 초로 떨어져야 직관적 |
| 6 | 통합 테스트 | 없음 | knot 엔드포인트 미사용. demo k6가 e2e 역할 |
| 7 | k6 시나리오 수 | 1개 (boundary burst) | demo의 유일한 학습 목표가 경계 burst |
| 8 | rules.yaml 변경 | 영구 변경 없음, demo 시 임시 override | knot 정책은 그대로 (redirect=token_bucket) |
| 9 | 시각 동기화 vs window 단축 | window=10초 + 무동기 demo | 분 단위 시각 동기화는 번잡. 짧은 window가 시연 본질 동일 |
| 10 | wiki 섹션 형태 | 짧은 1개 섹션 (경계 burst 위주) | demo lite 정신 — 다른 cycle의 9개 task 상세는 과함 |

## 7. 변경 파일 (T1~T4)

```
신규:
  experiments/knot/app/limiter/scripts/fixed_window.lua
  experiments/knot/app/limiter/fixed_window.py
  experiments/knot/tests/unit/test_fixed_window.py
  experiments/knot/load/fixed_window_boundary.k6.js
  experiments/knot/reports/fixed_window.md (+ PNG)
  experiments/knot/tmp_rules.yaml (gitignored, demo 실행 중에만 생성)

변경:
  experiments/knot/app/limiter/registry.py        # fixed_window 1줄 등록
  experiments/knot/.gitignore                     # tmp_rules.yaml 추가
  wiki/projects/knot.md                           # ## Cycle 2 짧은 섹션
  docs/specs/2026-05-24-rate-limiter-design.md   # §7 cycle 2 status: todo → done
  log.md                                          # cycle 2 완료 항목
```

**핵심 미변경**: `experiments/knot/rules.yaml` — knot 정책은 cycle 1 그대로 유지.
