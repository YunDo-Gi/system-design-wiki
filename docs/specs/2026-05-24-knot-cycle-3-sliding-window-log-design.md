# knot Cycle 3 — Sliding Window Log 설계

- **문서 종류**: Sub-spec (cycle 3, full)
- **상위 spec**: `docs/specs/2026-05-24-rate-limiter-design.md`
- **작성일**: 2026-05-24
- **관련 위키**: [[sliding-window-log-algorithm]], [[ch04-rate-limiter]], [[redis]]
- **상태**: 작성 직후

## 0. 목적과 학습 의도

[[sliding-window-log-algorithm]]을 knot의 `shorten` 엔드포인트(현재 `always_allow`)에 끼우고, **[[ch04-rate-limiter]] §"race condition"의 두 번째 표준 해법(Redis sorted set + Lua)**을 직접 구현. cycle 2 fixed window의 "경계 burst" 한계를 sliding window가 어떻게 해결하는지를 같은 boundary burst 시나리오로 비교 그래프 생성.

이 사이클 끝나면:
- `shorten` 엔드포인트가 sliding window log로 운영 (10 req/minute, 엄격)
- 4개 k6 시나리오(burst·ramp·cycle·boundary replay)로 sliding window 4가지 성질 시각화
- cycle 2 fixed_window 차트와 cycle 3 boundary replay 차트를 나란히 두면 **"왜 sliding window가 만들어졌나"**가 그림으로 즉시 박힘
- race demo로 ZSET + Lua atomicity 직접 증명

## 1. Sliding Window Log 알고리즘 (참조)

ch04 의사코드:

```
1. now = current time
2. ZREMRANGEBYSCORE key 0 (now - window_size)   # 윈도우 밖 timestamp 제거
3. count = ZCARD key                             # 윈도우 안 카운트
4. if count >= limit: deny + retry_after
5. else: ZADD key now uuid; allow
6. EXPIRE key (window_size + buffer)
```

핵심 성질:
- **경계 burst 없음** — 윈도우가 임의 시점 기준 직전 N초 (모든 요청마다 동적 결정). 정확한 rate 보장
- **메모리 비싸다** — 윈도우 안 모든 timestamp 보관. limit=10/min이면 사용자당 최대 10 entry. limit=1000/min이면 1000 entry
- **정확도: 높음** — ch04 비교표 셀

## 2. Storage layout

```
key:    knot:swl:{endpoint}:{identity}     예: knot:swl:shorten:api_key=abc
type:   Sorted Set (ZSET)
member: f"{ts_microseconds}-{random_hex_4}"  예: "1716543210123456-a3f9"
score:  ts_microseconds (float)
TTL:    ceil(window_size + 5초 buffer)
```

**Member 형식 결정** (Q1):
- 같은 microsecond에 두 요청 → score 동일 → ZADD member가 유니크해야 둘 다 저장됨
- `f"{ts}-{random}"` — 충돌 사실상 0, ZSET 메모리 entry당 약 28바이트 (string member 18~20 + score 8)
- 대안 C(ts 그대로)는 race demo에서 거짓 통과 — 정확히 우리가 막아야 할 시나리오

## 3. Atomic 연산 — Lua script

```lua
-- KEYS[1] = ZSET key (knot:swl:endpoint:identity)
-- ARGV[1] = limit (int)
-- ARGV[2] = window_size_seconds (int)
-- ARGV[3] = random_hex (4-char from Python, 충돌 회피)
-- returns: {allowed (0|1), limit, remaining, retry_after_ms}

local now_pair = redis.call('TIME')
local now_us = tonumber(now_pair[1]) * 1000000 + tonumber(now_pair[2])  -- microseconds

local window_size = tonumber(ARGV[2])
local window_us = window_size * 1000000
local cutoff = now_us - window_us

-- 1) 윈도우 밖 제거
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, cutoff)

-- 2) 현재 카운트
local count = redis.call('ZCARD', KEYS[1])
local limit = tonumber(ARGV[1])

local allowed = 0
local remaining = 0
local retry_after_ms = 0

if count < limit then
  -- 3) 추가
  local member = tostring(now_us) .. '-' .. ARGV[3]
  redis.call('ZADD', KEYS[1], now_us, member)
  allowed = 1
  remaining = limit - count - 1
else
  -- 4) 거부 — 가장 오래된 timestamp가 윈도우 밖으로 나갈 때까지 대기
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

cycle 1·2와의 차이:
- TIME microsecond 정밀도 사용 (sliding window는 ms 단위로 sliding)
- Sorted set 3개 명령(ZREMRANGEBYSCORE + ZCARD + ZADD)을 Lua로 묶음 → atomic
- `retry_after_ms`는 **가장 오래된 timestamp가 윈도우 밖으로 나갈 때까지** = 정확한 재시도 시각

## 4. Python 측 인터페이스

```python
# app/limiter/sliding_window_log.py
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

cycle 1·2와 동일 구조 — stale Script client binding, lazy register, key prefix 변환. 한 가지 추가: `secrets.token_hex(2)`로 4글자 hex 생성하여 Lua에 전달.

## 5. 테스트 전략

### Unit (`tests/unit/test_sliding_window_log.py`) — 4개

- `test_basic_pass_then_deny` — limit=5, 5번 통과 + 6번째 deny
- `test_no_boundary_burst` — **cycle 2와 정반대 시연**: 분 경계 전후 5+5 호출 시 두 번째 5개 중 처음 일부만 통과 (sliding window가 보호)
- `test_window_slides_continuously` — 1초 차이로 5번 호출, 1초 후 1개 더 호출 시 가장 오래된 게 빠져나가 통과
- `test_retry_after_accurate` — limit 소진 후 retry_after_ms가 정확히 (oldest + window - now) 값인지 검증

### Integration (`tests/integration/test_sliding_window_log_redis.py`) — 3개

- `test_shorten_burst_throttled` — `POST /shorten`을 10회 연속 호출 → 10 통과, 11번째 429 (shorten은 분당 10)
- `test_race_condition_atomic_zset` — `asyncio.gather` 50 동시 POST (limit=10) → 정확히 10 통과 (Lua + ZSET atomicity 증명)
- `test_identity_isolation` — 다른 API key는 별도 ZSET

### Load (k6, 4개 시나리오)

`load/sliding_window_log.k6.js`:

1. **burst** — cycle 1과 동일 패턴 (200 spike). sliding window는 정확히 limit만 통과
2. **ramp** — 1분간 0→100rps 증가
3. **steady_burst_cycle** — 1초 burst + 5초 휴식 ×3
4. **boundary_burst_replay** — **cycle 2와 동일한 시나리오** (12초간 200rps, 분 경계 통과). sliding window는 spike-spike 패턴이 아닌 **균등 throttle** 보여야 함

### Report

`reports/sliding_window_log.md` + 4개 차트 (각 시나리오 1개). `scripts/report.py` 그대로 재사용.

## 6. rules.yaml 변경

```yaml
descriptors:
  - key: endpoint
    value: shorten
    rate_limit:
      algorithm: sliding_window_log    # ← 변경
      unit: minute
      requests_per_unit: 10
  - key: endpoint
    value: redirect
    rate_limit:
      algorithm: token_bucket          # cycle 1 그대로
      unit: second
      requests_per_unit: 50
      burst: 100
```

**완성**: cycle 3 끝나면 knot의 두 엔드포인트가 각각 자기에게 적합한 알고리즘을 사용. shorten=엄격(쓰기·악용 방지), redirect=관대(읽기·UX 우선).

## 7. 결정 이력 (Decision Log)

| # | 결정 | 선택 | 이유 |
|---|---|---|---|
| 1 | Cycle 3 형태 | full | shorten 엔드포인트가 실제 사용. cycle 1과 동등 학습 깊이 필요 |
| 2 | 원자 연산 | Lua + ZSET 3명령 (ZREMRANGEBYSCORE + ZCARD + ZADD) | ch04 §"race condition" 2번째 표준 해법. cycle 1 Lua 패턴 재사용 |
| 3 | ZSET member 형식 | `f"{ts_us}-{random_hex_4}"` | 같은 ms에 두 요청 충돌 회피. ch04는 명시 안 함 (textbook 묵시 가정 보강) |
| 4 | 시각 정밀도 | microsecond (TIME의 sec*1e6 + microsec) | sliding window는 ms 단위 sliding이 본질 |
| 5 | retry_after 계산 | `(oldest + window - now)` from ZRANGE 0 0 WITHSCORES | 가장 오래된 timestamp가 빠져나갈 정확한 시각 |
| 6 | k6 시나리오 수 | 4개 (cycle 1의 3개 + boundary replay) | cycle 2와 직접 비교로 sliding window의 핵심 가치 시각화 |
| 7 | 단위 테스트 4개 | basic, no_boundary_burst, slides_continuously, retry_after_accurate | cycle 2 한계 부재 + sliding 본질 + retry 정확성 |
| 8 | shorten 정책 강도 | limit=10/minute, mode=hard | 쓰기 + 악용 방지. cycle 5 hard/soft에서 mode 활용 |
| 9 | TTL | `window_size + 5초 buffer` | cycle 2와 동일 패턴 |
| 10 | ZSET 메모리 우려 | 본 사이클에선 검증만 — 회고(cycle 7)에서 sliding_counter와 비교 | 한도가 작아 메모리 부담 없음. 큰 한도에선 우려, 그래서 sliding_counter가 존재 |

## 8. 변경 파일 (T1~T9)

```
신규:
  experiments/knot/app/limiter/scripts/sliding_window_log.lua
  experiments/knot/app/limiter/sliding_window_log.py
  experiments/knot/tests/unit/test_sliding_window_log.py
  experiments/knot/tests/integration/test_sliding_window_log_redis.py
  experiments/knot/load/sliding_window_log.k6.js
  experiments/knot/reports/sliding_window_log.md (+ PNG들)

변경:
  experiments/knot/app/limiter/registry.py        # 1줄
  experiments/knot/rules.yaml                     # shorten → sliding_window_log
  experiments/knot/tests/integration/test_middleware_e2e.py  # shorten 헤더 기대값 갱신
  wiki/projects/knot.md                           # ## Cycle 3 섹션 append
  docs/specs/2026-05-24-rate-limiter-design.md   # §7 cycle 3 status: todo → done
  log.md                                          # cycle 3 항목
```

## 9. 미해결 / 후속

- **메모리 사용량 측정**: 한도 큰 케이스(예: 10000/min)에서 ZSET이 차지하는 메모리를 cycle 7 회고에서 실측 + sliding_counter가 어떻게 줄이는지 정리
- **윈도우 정확도 한계**: ms 정밀도라 ns 단위 race는 보호 안 됨. 실서비스 무관, 학습용 참고
- **Lua script 길이 증가**: ZSET 3명령 + TIME + ZRANGE → cycle 1 token_bucket보다 길지만 여전히 ~30줄. 더 길어지면 module화 고려
