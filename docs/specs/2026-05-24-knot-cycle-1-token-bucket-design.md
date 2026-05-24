# knot Cycle 1 — Token Bucket 설계

- **문서 종류**: Sub-spec (cycle 1 한정)
- **상위 spec**: `docs/specs/2026-05-24-rate-limiter-design.md`
- **작성일**: 2026-05-24
- **관련 위키**: [[token-bucket-algorithm]], [[ch04-rate-limiter]], [[redis]]
- **상태**: 작성 직후 (구현 미착수)

## 0. 목적

[[token-bucket-algorithm]]을 knot 위에 plug-in으로 끼우고, **k6 부하 실측으로 ch04 비교표의 "버스트 허용" 특성을 눈으로 확인**한다. 동시에 k6·matplotlib 리포트 생성 도구를 1회 셋업해 cycle 2~5가 같은 도구로 가볍게 굴러가게 만든다.

이 사이클 끝나면:

- `redirect` 엔드포인트가 token bucket 정책으로 운영됨 (rate 50/s, burst 100)
- 부하 그래프(`reports/token_bucket.md`)로 burst 흡수·refill 동작 시각화
- race condition 데모(asyncio.gather 100 동시) 통합 테스트 통과
- 사이클 2~5는 알고리즘 모듈만 추가하면 같은 도구 chain으로 리포트 자동 생성

## 1. Storage layout

Redis HASH 1개 per (endpoint × identity).

```
key:    knot:bucket:{endpoint}:{identity}     예: knot:bucket:redirect:1.2.3.4
type:   HASH
fields:
  tokens         (float)  현재 남은 토큰 수
  last_refill    (float)  마지막 리필 시각 (Redis 서버 epoch seconds)
TTL:    ceil(capacity / rate * 2)             오래 안 쓰면 만료, 메모리 회수
```

**왜 HASH인가** — `tokens`와 `last_refill` 두 필드를 한 명령(`HMGET`/`HMSET`)으로 묶을 수 있어 Lua 스크립트가 짧아짐. 별도 키 2개로 분리하면 atomic 보장은 Lua 안에서 어차피 되니 문제없지만 코드가 길어짐.

**TTL 산정** — 한 사용자가 `capacity / rate * 2`초 이상 안 들어오면 bucket을 0으로 다시 초기화해도 무방 (이미 풀로 회복돼있어야 할 시간의 2배). 메모리 회수 + 비활성 사용자 데이터 누적 방지.

## 2. Atomic 연산 — Lua script

```lua
-- KEYS[1] = bucket key (knot:bucket:...)
-- ARGV[1] = capacity (int)
-- ARGV[2] = refill_rate (tokens/sec, float)
-- ARGV[3] = cost (int, 보통 1)
-- 반환: {allowed (0|1), remaining (int, 내림), retry_after_ms (int)}

local now_pair = redis.call('TIME')                       -- {sec, microsec}
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

**파일 위치**: `experiments/knot/app/limiter/scripts/token_bucket.lua` — Python 문자열에 넣지 않고 별도 파일로. LSP·diff·재사용성 ↑. Python 측은 import 시 1회 읽어서 `script_load`로 SHA 캐시.

**EVALSHA 우선, EVAL fallback** — 매 호출 SHA만 전송(빠름). Redis가 script flush로 SHA를 잃어버리면 `NOSCRIPT` 에러 발생 → EVAL로 재실행. redis-py가 `Script` 객체로 이미 이 패턴을 추상화하고 있으니 그걸 사용.

## 3. Python 측 인터페이스

```python
# app/limiter/token_bucket.py
from pathlib import Path
from app.limiter.base import Decision, Rule
from app.redis_client import get_redis

_SCRIPT = (Path(__file__).parent / "scripts" / "token_bucket.lua").read_text()


class TokenBucket:
    def __init__(self) -> None:
        self._script = get_redis().register_script(_SCRIPT)

    async def allow(self, key: str, rule: Rule) -> Decision:
        capacity = rule.burst or rule.requests_per_unit
        rate = rule.requests_per_unit / _unit_seconds(rule.unit)
        bucket_key = f"knot:bucket:{key.split(':', 1)[1]}" if ":" in key else f"knot:bucket:{key}"
        # key 형식: "knot:redirect:1.2.3.4" → bucket key: "knot:bucket:redirect:1.2.3.4"
        bucket_key = key.replace("knot:", "knot:bucket:", 1)

        allowed, remaining, retry_ms = await self._script(keys=[bucket_key], args=[capacity, rate, 1])
        return Decision(
            allowed=bool(allowed),
            limit=capacity,
            remaining=int(remaining),
            retry_after=retry_ms / 1000.0,
        )
```

**`rule.burst` vs `rule.requests_per_unit`** — token bucket은 두 파라미터 분리가 본질:
- `requests_per_unit` (예: `50/second`) = **리필 속도**
- `burst` (예: `100`) = **버킷 용량** (순간 최대치)
- `burst` 미지정 시 `requests_per_unit`을 capacity로 사용 (= 버스트 없음)

**`Decision.limit`은 capacity로** — 응답 헤더 `X-Ratelimit-Limit`이 의미하는 건 "현재 한도"인데, 사용자 입장에서 직관적인 건 평균 rate가 아니라 capacity. 단, 시간당 평균은 `rate`로 결정되므로 헤더에 그것도 노출할지는 후속 결정 (현재는 capacity만).

## 4. 테스트 전략

### Unit (`tests/unit/test_token_bucket.py`)

도구: `fakeredis>=2.21` + `freezegun`.

| 검증 | 시나리오 |
|---|---|
| 첫 호출 | empty bucket → capacity로 초기화, 1개 차감, allowed=True |
| Burst 흡수 | 0초에 capacity회 연속 호출 → 모두 allowed, capacity+1번째 → denied |
| Refill | denied 후 `freezegun`으로 시계 advance → 토큰 회복, allowed로 전환 |
| 한계 초과 회복량 | 매우 긴 시간 advance → tokens는 capacity로 capped (over-fill 방지) |
| `retry_after` 계산 | denied 시점에 (cost - tokens) / rate가 정확한지 |

**왜 fakeredis인가** — 결정적·빠름. `freezegun`으로 frozen time + fakeredis의 in-memory state로 알고리즘 본질만 검증.

**한계** — `redis.call('TIME')`은 fakeredis에서 Python 시각을 반환하는데, `freezegun`이 fakeredis 내부의 시각 호출을 가로채는지 검증 필요. 미작동하면 fallback으로 `time.time` monkeypatch.

### Integration (`tests/integration/test_token_bucket_redis.py`)

도구: 실제 Redis (docker-compose) + httpx AsyncClient.

| 검증 | 시나리오 |
|---|---|
| e2e 응답 | `GET /{code}` capacity회 → 200 + 헤더, capacity+1번째 → 429 + Retry-After |
| Race condition | `asyncio.gather`로 동시 200 요청 (capacity=100) → 정확히 100개만 통과, 100개 429 |
| Refill 실시간 | 거부 → 1초 sleep → 다시 호출 → 50개 통과 (rate=50/s 가정) |
| Identity 격리 | 다른 `X-API-Key`로 보낸 요청은 별도 bucket |

**Race condition 테스트의 가치** — Lua script atomicity의 직접 증명. 만약 atomic이 깨지면 200개 모두 통과하는 false-positive 발생. ch04 §"race condition" 코드 증명의 1단계.

### Load (k6, `load/token_bucket.k6.js`)

3개 시나리오를 한 파일에 `scenarios`로 묶어 명시적 stage 정의:

1. **`burst`** — 0초에 200req 폭주 (가상 사용자 200, 1초 내 완료). 처음 capacity 통과, 나머지 429.
2. **`ramp`** — 1분 동안 0 → 100rps 선형 증가. rate(50/s) 초과부터 429 비율 ↑.
3. **`steady_burst_cycle`** — `1초 100req → 5초 휴식` × 3회. 휴식 동안 refill, 다음 burst가 다시 통과.

**왜 이 3개** — token bucket의 시그니처(burst 흡수, 평균 rate 제한, refill 회복)를 각각 격리해서 시연. cycle 2(leaking bucket) 이후엔 같은 3개 시나리오를 alg만 바꿔 돌려 비교 그래프.

### Report (`scripts/report.py` + `reports/token_bucket.md`)

스크립트: k6 JSON output(`--out json=...`) → pandas로 시간버킷 집계 → matplotlib 3개 PNG → 마크다운 템플릿에 embed.

차트:
- ① 시간별 통과·거부 카운트 (stacked bar)
- ② `X-Ratelimit-Remaining` 시간 추이 (line) — 버킷이 비고 차는 패턴
- ③ 시나리오별 통과율·p50/p95 지연 (표)

**스크립트는 알고리즘 무관** — `--report-name`만 받아서 `reports/<name>.md` 생성. cycle 2~5에서 재사용.

## 5. rules.yaml 변경

```yaml
descriptors:
  - key: endpoint
    value: shorten
    rate_limit:
      algorithm: always_allow           # cycle 4에서 sliding_window_log로
      unit: minute
      requests_per_unit: 10
  - key: endpoint
    value: redirect
    rate_limit:
      algorithm: token_bucket           # ← cycle 1 변경
      unit: second
      requests_per_unit: 50             # rate
      burst: 100                        # capacity
```

`shorten`은 손대지 않음. **사이클별 변경 1개 원칙** — diff와 학습 단위를 작게.

## 6. 에러 처리

cycle 0 spec §5(상위)의 fail-open 정책을 그대로 따른다. 추가로:

| 상황 | 동작 |
|---|---|
| Lua `NOSCRIPT` (Redis가 script 캐시 잃음) | redis-py `Script`가 자동 EVAL fallback → 정상 처리 |
| `rule.burst` 없음 | capacity = `requests_per_unit` (버스트 없는 token bucket = 의미상 leaky bucket과 유사) |
| `rule.burst < requests_per_unit` | 경고 로그 (이상한 설정이지만 동작은 함) |
| `rule.unit`이 알 수 없는 값 | 시작 시 `load_rules()`가 던짐 (rule 검증을 거기서 강화 — cycle 1에 포함) |

## 7. 결정 이력 (Decision Log)

| # | 결정 | 선택 | 이유 |
|---|---|---|---|
| 1 | Cycle 1 스코프 | Full (코드 + 단위 + 통합 + race demo + k6 + matplotlib 리포트) | k6/matplotlib 셋업의 1회성 부담을 cycle 1에서 흡수. cycle 2~5는 모듈만 추가하면 같은 도구 chain으로 가벼움 |
| 2 | 원자 연산 방식 | Lua script + `EVALSHA` (fallback `EVAL`) | [[ch04-rate-limiter]] §"race condition"의 1순위 권장. cycle 4 sliding window log, cycle 7 hard/soft에서도 재사용. "락 안 쓴다" 원칙 직접 시연 |
| 3 | 시각 출처 | Lua 안에서 `redis.call('TIME')` | 다중 노드 clock skew 면역. 상위 spec §5의 sliding window 패턴과 통일. Redis 5+에서 `replicate_commands` 또는 effects replication(7+)으로 안전. redis:7-alpine 사용 중 |
| 4 | 단위 테스트 Redis | `fakeredis>=2.21` + `freezegun` | 결정적·빠름. Lua 지원(2.0+). 알고리즘 본질만 격리 검증 |
| 5 | 통합 테스트 Redis | 실제 Redis (docker-compose) | fakeredis와 실 Redis의 Lua 동작 미세 차이를 잡음. race demo는 실제 Redis에서만 의미 있음 |
| 6 | Storage 자료구조 | HASH (tokens, last_refill 두 필드) | 한 명령(`HMGET`/`HMSET`)으로 묶음 — Lua 짧아짐. 별도 키 2개도 가능했지만 가독성 손해 |
| 7 | `shorten` 엔드포인트 | always_allow 유지 | cycle 4 sliding window log로 변경 예정. **사이클별 변경 1개 원칙** 으로 학습 단위 격리 |
| 8 | Lua script 저장 위치 | 별도 `.lua` 파일 (`app/limiter/scripts/token_bucket.lua`) | Python 문자열 임베드보다 LSP·diff·재사용성 ↑. 파일 import는 1회 |
| 9 | `Decision.limit` 의미 | `capacity` (rate가 아님) | 사용자 입장에서 직관적인 한도. `X-Ratelimit-Limit` 헤더 표준의 자연 해석 |
| 10 | TTL 산정 | `ceil(capacity / rate * 2)` | 풀로 회복되는 시간의 2배 안에 안 들어오면 메모리 회수. 활성 사용자엔 영향 없음 |
| 11 | Burst 미지정 시 동작 | `capacity = requests_per_unit` | burst 없는 token bucket = 의미상 leaky와 유사. 명시적 fallback |
| 12 | k6 시나리오 3종 | burst·ramp·steady-burst-cycle | token bucket의 시그니처(흡수·평균 한계·회복)를 각각 격리 시연. cycle 2~5에서 alg만 바꿔 재사용 |

## 8. 변경 파일 요약 (T1~T10에서 다룰 것)

```
신규:
  experiments/knot/app/limiter/scripts/__init__.py
  experiments/knot/app/limiter/scripts/token_bucket.lua
  experiments/knot/app/limiter/token_bucket.py
  experiments/knot/tests/unit/test_token_bucket.py
  experiments/knot/tests/integration/test_token_bucket_redis.py
  experiments/knot/load/__init__ (디렉터리)
  experiments/knot/load/token_bucket.k6.js
  experiments/knot/scripts/__init__ (디렉터리)
  experiments/knot/scripts/report.py
  experiments/knot/reports/__init__ (디렉터리)
  experiments/knot/reports/token_bucket.md (생성됨)
  experiments/knot/reports/token_bucket_*.png (3개)

변경:
  experiments/knot/app/limiter/registry.py        # token_bucket 1줄 추가
  experiments/knot/rules.yaml                     # redirect만 알고리즘 변경
  experiments/knot/app/rules.py                   # unit 값 검증 강화
  experiments/knot/pyproject.toml                 # dev deps: freezegun, pandas, matplotlib
  experiments/knot/README.md                      # 새 도구 사용법 짧게 추가
  wiki/projects/knot.md                           # ## Cycle 1 섹션 append
  docs/specs/2026-05-24-rate-limiter-design.md   # §7 cycle 1 status: todo → done
  log.md                                          # cycle 1 완료 항목 append
```

## 9. 미해결 / 후속

- **TIME 명령의 fakeredis 호환**: 위 §4 unit 한계 참조. T3에서 검증, 안 되면 monkeypatch 대안.
- **`scripts/report.py`의 차트 디테일** — 첫 사이클은 단순(3개 PNG + 표). cycle 2부터 알고리즘 간 overlay 차트가 필요해질 텐데 그때 확장.
- **`X-Ratelimit-Reset` 헤더 (다른 표준)**: ch04는 명시 안 함. 현재 안 박음. 사이클 8 클라이언트 SDK에서 필요해지면 추가.
- **Burst가 `requests_per_unit`보다 작으면 경고만**: 막을지는 cycle 7 hard/soft 논의 시 재검토.
