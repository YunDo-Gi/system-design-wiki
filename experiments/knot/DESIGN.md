# knot — 설계 회고 (cycle 0~4 진행 요약)

> Alex Xu, *System Design Interview 2nd ed.* **Chapter 4 — Design a Rate Limiter**를 손으로 검증하기 위한 학습 프로젝트의 설계 요약.
>
> - 코드: `app/`
> - 사이클별 task·결정·함정 기록: `../../wiki/projects/knot.md`
> - 사이클별 sub-spec: `../../docs/specs/2026-05-24-knot-cycle-N-*.md`
> - 상위 spec: `../../docs/specs/2026-05-24-rate-limiter-design.md`
>
> 본 문서는 **코드 디테일을 빼고** 설계 결정·ch04 매핑·테스트 시나리오·실측 결과 중심으로 정리. 1~2년 후 다시 봐도 "이걸 왜 이렇게 만들었나, 어떻게 검증했나"가 자족적으로 파악되도록.

## 1. 프로젝트 개요

### 1-1. 왜 만들었나

ch04는 알고리즘 5개와 분산 환경 이슈를 글·의사코드·비교표로 설명. 학습 효과를 강화하기 위해 **책 본문을 그대로 코드로 옮기고 부하 실측으로 검증**하는 게 목표. 가상 서비스 **knot**(URL 단축 SaaS mock)을 깔고, 그 위에 rate limiter 미들웨어를 사이클별로 진화시킴.

### 1-2. 비목표

- 실제 운용 가능한 URL 단축 서비스 (단축 로직은 in-memory mock)
- 분산 limiter 다 노드 시연 (ch05 일관된 해싱·ch06 KV 주제와 겹침 — 회고에서 정리)
- 멀티 DC eventual consistency, OSI L3 차단 (회고 노트로만)

### 1-3. 사이클 로드맵 (원안 → 갱신)

**원안**: 9 사이클 (5 알고리즘 각 full + 운영 4)
**갱신** (cycle 1 후 회고): **7 사이클** — knot 엔드포인트가 실제 쓰는 알고리즘만 full, 나머지는 demo lite 또는 회고에서 글로

| # | 사이클 | 형태 | 상태 |
|---|---|---|---|
| 0 | Foundation (plug-in 셋업) | full | ✅ |
| 1 | Token bucket (redirect) | full | ✅ |
| 2 | Fixed window (경계 burst demo) | **demo lite** | ✅ |
| 3 | Sliding window log (shorten) | full | ✅ |
| 4 | 다차원 규칙 + 핫리로드 | full | ✅ |
| 5 | hard vs soft 정책 | full | 진행 중 |
| 6 | 클라이언트 SDK | full | 예정 |
| 7 | 회고 (스킵된 알고리즘 + multi-DC·OSI L3·edge) | wiki 글 | 예정 |

스킵된 알고리즘 두 개:
- **leaking_bucket** — token bucket의 거울. 그래프 차이만 보여주는 수준이라 회고 글로
- **sliding_window_counter** — sliding log의 근사. cycle 3로 핵심은 커버, 회고에서 메모리 트레이드오프 비교

## 2. 가상 서비스 — knot

### 2-1. 두 엔드포인트

| | `POST /shorten` | `GET /{code}` |
|---|---|---|
| 동작 | URL 입력받아 코드 발급 | 코드로 원본 URL 302 redirect |
| 부하 특성 | 쓰기, 빡빡 | 읽기 (압도적으로 많음), 헐겁 |
| 식별자 | `X-API-Key` | 익명 IP |
| 알고리즘 (cycle 3 후) | **sliding_window_log** (엄격, 분당 10) | **token_bucket** (관대, burst 100) |
| ch04에서 어느 셀 | "정확도: 높음" | "버스트: 허용" |

같은 앱 안에 정반대 성격의 두 엔드포인트를 두는 게 핵심 설계. **한 시스템 안에 알고리즘 두 개가 공존**하므로 plug-in 추상화가 필요함을 자연 동기로 부여.

### 2-2. 향후 진화 (ch05~08 주제)

실서비스는 두 경로의 부하 차가 너무 커서 거의 항상 분리:
- `redirect`는 edge CDN/read replica/KV → ch05 일관된 해싱, ch06 KV store
- `shorten`은 중앙 write service → ch07 unique ID generator, ch08 URL Shortener

본 cycle은 미들웨어가 엔드포인트별 다른 정책을 적용 가능하게 설계 → ch08 시점에 양쪽 서비스로 rate limiter 코드 거의 그대로 이식 가능.

## 3. 핵심 설계 결정 (전체 사이클을 관통하는 4가지)

### 3-1. `Limiter` Protocol — 알고리즘 plug-in

ch04 §"알고리즘 비교" 표가 5개 알고리즘이 **같은 입출력 인터페이스**를 가진다고 전제. 우리는 그 전제를 코드로 명문화:

- `Rule` (NamedTuple): 정책 입력 — `algorithm`, `unit`, `requests_per_unit`, `burst`, `mode`
- `Decision` (NamedTuple): 판정 출력 — `allowed`, `limit`, `remaining`, `retry_after`
- `Limiter` (Protocol): `async def allow(key, rule) -> Decision`

`Decision`의 4개 필드가 ch04 §"클라이언트 응답 형식" 표준 헤더(`X-Ratelimit-Limit/Remaining/Retry-After` + 429 분기)와 1:1 매핑. **알고리즘 내부가 무엇이든 클라이언트에 노출되는 정보는 표준화** — ch04의 추상화 경계.

### 3-2. Redis 단일 저장소 + Lua atomic

ch04 §"분산 환경의 race condition"이 명시한 두 표준 해법:
1. **Lua script** — 여러 명령을 한 덩어리로 atomic 실행 (cycle 1 token bucket, cycle 3 sliding window log, cycle 2 fixed window)
2. **Sorted set** — sliding window log의 자료구조 (cycle 3)

우리는 모든 알고리즘이 **단일 `allow()` 호출 안에서 Lua 한 번**으로 완료되도록 구현. 락 사용 0회.

또한 ch04 §"분산 환경의 Synchronization"의 권고("**여러 limiter 노드가 정책이 어긋나지 않으려면 중앙 공유 저장소**")를 위해 모든 카운터를 단일 Redis에 둠. 노드 N개로 확장해도 정책 일관성 유지.

### 3-3. Rules-as-Data (Lyft envoy 포맷)

ch04 §"기본 아키텍처"가 Lyft 오픈소스 yaml 포맷을 인용. cycle 0에서 단순 평면 lookup으로 시작, cycle 4에서 **중첩 descriptors로 다차원 매칭**으로 확장.

- 시작 시 yaml 로드 + watchdog 파일 watcher로 **즉시 핫리로드** (cycle 4)
- 매칭 우선순위: **가장 구체적(depth 큰)** 우선 — Lyft envoy 동작과 동일
- atomic swap (새 Rules 객체 통째 교체) — 실패 시 이전 정책 유지

### 3-4. 미들웨어 위치 (in-process)

ch04 §"위치/배치" 표의 마지막 행("API gateway 미들웨어")의 **in-process 버전**. FastAPI `BaseHTTPMiddleware`로 마운트. ch08 시점엔 Envoy/Nginx 같은 외부 gateway로 옮길 수 있게 추상화는 동일.

**왜 in-process를 선택했나**: 학습 목적상 알고리즘 코드를 직접 보고 실행할 수 있어야 함. Envoy 쓰면 `config.yaml`에 한 줄 적고 끝. 우리는 token bucket이 어떻게 동작하는지 의사코드 → Lua → 부하 실측의 닫힌 루프를 거쳐야 의미 있음.

## 4. 사이클별 진화 (cycle 0~4)

### Cycle 0 — Foundation

**무엇을 만들었나**: FastAPI 앱, mock 핸들러, 미들웨어 셸, 규칙 로더, Redis docker-compose, "always-allow" dummy limiter, 429 헤더 표준.

**핵심 설계 결정**:
- Protocol/Registry/Rules 3층 분리 — cycle 1~5에서 알고리즘 추가는 모듈 1개 + registry 1줄 + yaml 1줄
- 모든 카운터 상태는 Redis로 — 인스턴스는 stateless
- `KNOT_RULES_PATH` env override (cycle 2에서 도입, cycle 4 핫리로드 사전 셋업)

**무엇을 검증했나**: 10개 테스트 (unit 6 + integration 4) — interface 흐름, lifespan/startup, 미들웨어 헤더 주입, Redis 연결.

**ch04 매핑**: 알고리즘 아닌 부분 — middleware 패턴, 헤더 표준, Redis 단일 저장소.

### Cycle 1 — Token Bucket (`/redirect` 활성화)

**무엇을 만들었나**: Lua script (HASH 자료구조: `tokens` + `last_refill`), Python wrapper, k6 burst/ramp/cycle 시나리오 3개, matplotlib 리포트.

**핵심 설계 결정**:
- 시각 출처: **`redis.call('TIME')`** Lua 안에서 — 다중 노드 clock skew 면역
- 자료구조: HASH 1개로 두 필드를 묶음 (HMGET/HMSET 한 명령) → Lua 짧아짐
- 단위 테스트: fakeredis + freezegun (lupa extra 필요 — 함정 1)
- 통합 테스트: 실 Redis + asyncio.gather race demo
- TTL: `capacity / rate * 2`초 — 풀 회복 시간의 2배 비활성 시 메모리 회수

**테스트 시나리오와 결과**:

**Unit 5개** — 알고리즘 본질 검증
1. `test_first_call_initializes_full_bucket`: 빈 상태 첫 호출 → capacity만큼 토큰 초기화
2. `test_burst_absorbs_capacity_then_denies`: 0초에 capacity회 연속 → 모두 통과, capacity+1번째 → deny
3. `test_refill_after_time_advance`: deny 후 freezegun으로 시계 advance → 토큰 회복 → 통과 전환
4. `test_overfill_capped_at_capacity`: 1시간 비활성 후도 capacity까지만 (`math.min` cap 검증)
5. `test_identities_have_separate_buckets`: 다른 식별자는 독립 bucket

**Integration 3개** — middleware + 실 Redis 통합
1. `test_redirect_burst_absorption`: 순차 105회 → 100 통과 + 5 거부 (burst 흡수)
2. `test_race_condition_atomic`: **asyncio.gather 200 동시 (capacity=100)** → **passed=101 / denied=99**. +1은 dispatch ~20ms 동안 50tok/s × 0.02s = 1 토큰 리필. **Lua atomic 아니었다면 200 모두 통과**했을 것 — ch04 §"race condition" 직접 증명
3. `test_identity_isolation`: 다른 API key는 별도 bucket

**Load — k6 3 시나리오 (총 4,099 요청, p95 7.88ms)**:

| scenario | total | denied | pass_rate | 시그니처 검증 |
|---|---:|---:|---:|---|
| burst (200 spike) | 200 | 84 | **58%** | capacity 100 흡수 + 거부 — "**버스트 허용**" 셀 |
| ramp (0→100rps in 60s) | 2,999 | 651 | **78%** | rate 50/s 초과 지점부터 거부 — "정확도: 중" |
| steady_burst_cycle (1s 100req + 5s 휴식 ×3) | 900 | 0 | **100%** | 5초 휴식 동안 250 토큰 생성(50/s×5) → capacity 100으로 cap → 다음 burst 100% — refill 로직 직접 확인 |

→ [[token-bucket-algorithm]] 비교표 한 행이 그래프로 증명됨.

**ch04 본문에 없는 발견 (학습 자산)**:
- `fakeredis` Lua = `lupa` 패키지 필요
- redis-py `Script`의 **stale client binding** (close 후 새 클라이언트면 stale → re-register 패턴 필수)
- `httpx.ASGITransport`는 `request.client.host` 공통 → API key로 명시 격리 필요

### Cycle 2 — Fixed Window Counter (demo lite, 경계 burst 시연)

**왜 demo lite인가**: knot 엔드포인트가 fixed_window를 안 씀 (운영용으로 부적합 — 경계 burst). 하지만 **ch04 비교표 셀 "정확도: 낮음 (경계 burst)"이 무엇인지 글로만 봐선 안 박힘** → 그래프 한 장 시연이 학습 목표.

**무엇을 만들었나**: Lua script (string 카운터: `INCR` + `EXPIRE`), Python wrapper, k6 boundary_burst 시나리오 1개, 짧은 report (4 task — full cycle의 ~1/4 시간).

**핵심 설계 결정**:
- 자료구조: string 카운터 (HASH 불필요 — 단일 정수)
- `window_start = floor(now / window_size) * window_size` — 모든 사용자·요청이 같은 윈도우 슬롯 시각을 보게 됨. **이게 경계 burst의 원인**
- 엔드포인트 정책 영구 변경 X — demo 실행 시 임시 `tmp_rules.yaml`로 override (`KNOT_RULES_PATH` env 활용)
- 부수 산출: `app/main.py`에 `KNOT_RULES_PATH` env override 도입 — cycle 4 핫리로드 사전 셋업

**테스트 시나리오와 결과**:

**Unit 3개**:
1. `test_basic_pass_then_deny`: limit=5, 5번 통과 + 6번째 deny
2. `test_boundary_burst_demonstrates_2x` — **핵심 시연**: 12:00:59에 5 통과, 1초 흘러 12:01:00에 5 통과 → **2초 구간에 10 통과 (분당 5의 2배)**. fixed window 한계가 unit test로 codify
3. `test_window_isolation_no_carryover`: 한 윈도우 소진 후 다음 윈도우 fresh

**Load — k6 boundary_burst (12초간 200rps, 분 경계 통과)**:

- 총 2,401 요청, **200 통과 (8.33%)**, 2,201 거부 (91.67%)
- 차트에서 **두 통과 spike** 명확:
  - 11:33:53: 현재 윈도우 한도 100 흡수
  - 11:33:54~11:33:59: 6초간 전량 거부 (현재 윈도우 소진)
  - **11:34:00: 두 번째 spike — 새 분 윈도우 시작, 다시 100 흡수**
  - 11:34:01~11:34:04: 4초간 전량 거부
- **약 2초 구간에 의도(분당 100)의 2배인 200 요청 통과** — ch04 비교표 "정확도: 낮음 (경계 burst)" 셀의 그래프 증명

**부수 함정 (cycle 1 노트 누적 가치 검증)**:
- 포트 8000 충돌 (로컬 "Lemonade") → 8001 + env 주입
- pandas `dt.floor("S")` deprecated → 소문자 `"s"`
- `df.to_markdown()` ↔ `tabulate` 의존성

### Cycle 3 — Sliding Window Log (`/shorten` 활성화)

**무엇을 만들었나**: Lua script (sorted set: ZREMRANGEBYSCORE + ZCARD + ZADD를 한 Lua로 묶음), Python wrapper, k6 4 시나리오 (cycle 1의 3개 + boundary_burst_replay), report.

**핵심 설계 결정**:
- 자료구조: Redis sorted set — score=timestamp, member=`f"{ts_us}-{random_hex_4}"` (충돌 회피)
- 시각 정밀도: microsecond (sliding window는 ms 단위 sliding이 본질)
- `retry_after` 계산: 가장 오래된 timestamp가 윈도우 밖으로 나갈 시각 = `oldest + window - now`
- member 형식은 **ch04에 명시 없음** — textbook 묵시 가정("timestamps are unique")의 엔지니어링 보강

**테스트 시나리오와 결과**:

**Unit 4개**:
1. `test_basic_pass_then_deny`: limit=5, 5 통과 + 6번째 deny
2. `test_no_boundary_burst` — **cycle 2의 정확한 안티 시연**: 12:00:59에 5 통과 후 1초 흘러 12:01:00에 6번째 호출 → **거부** (직전 60초 윈도우에 이미 5개 있음). cycle 2가 EXPECTED했던 2배 burst를 cycle 3은 차단
3. `test_window_slides_continuously`: 1초 윈도우 내 3개 채움 → 1.1초 후 새 호출 통과 (가장 오래된 게 윈도우 밖)
4. `test_retry_after_accurate`: limit 소진 후 retry_after 정확 검증 — `(oldest_ts + window - now)` 공식 일치

**Integration 3개**:
1. `test_shorten_burst_throttled`: 11회 연속 POST → 정확히 10 통과 + 1 거부 (분당 10)
2. `test_race_condition_atomic_zset` — **핵심**: asyncio.gather 50 동시 (limit=10) → **passed=10 / denied=40, 0 jitter**. cycle 1 token bucket의 +1 jitter와 대조 — ZSET timestamp 엄격 비교라 dispatch 동안 어떤 토큰도 추가되지 않음. **더 정확한 atomic 증명**
3. `test_identity_isolation_shorten`: 다른 API key 별도 ZSET

**Load — k6 4 시나리오 (총 1,459 요청, p95 5ms)**:

각 VU에 다른 `x-api-key`를 주어 별도 bucket. limit=10/min이라 단일 키였다면 곧장 거부됨.

| scenario | total | denied | pass_rate | 시그니처 |
|---|---:|---:|---:|---|
| burst (20 VUs × 1 req) | 20 | 0 | 100% | VU별 별도 bucket, 각 1회만 |
| ramp (0→30rps in 60s, 다수 VU) | 899 | 599 | 33% | 시간 흐를수록 VU별 bucket 차서 deny 증가 |
| steady_burst_cycle (VU별 1s burst + 5s 휴식 ×3) | 179 | 0 | 100% | VU별 한도 내 |
| **boundary_burst_replay (12초 200rps)** | 361 | 161 | **55%** | **cycle 2와 동일 시나리오 — spike 없음** |

**가장 중요한 결과 — boundary_burst_replay 비교** (cycle 2 vs cycle 3, 같은 시나리오):

| | cycle 2 (fixed_window) | cycle 3 (sliding_window_log) |
|---|---|---|
| 차트 패턴 | spike-deny-spike (2 개 spike) | **smooth ramp → wall → resume** |
| 분 경계 처리 | 직후 추가 100 통과 (의도 2배) | **경계 무관 — 직전 60초 동적 윈도우** |
| ch04 비교표 | "정확도: 낮음" | "정확도: 높음" |

→ 같은 12초 입력에 두 알고리즘의 행동이 그래프로 극명히 달라짐. **ch04가 글로만 "sliding window는 fixed window 한계를 해결"이라 한 명제의 시각 증명**. cycle 7 회고에서 두 차트를 나란히 비교.

### Cycle 4 — 다차원 규칙 + 핫리로드 (운영 측면)

**무엇을 만들었나**: Rules 데이터 모델을 평면 dict → **RuleNode 트리 + DFS specificity matching**으로 리팩터. watchdog 파일 watcher 도입. middleware가 `X-User-Tier` 헤더 추출.

**핵심 설계 결정**:
- 2번째 차원: `user_tier` (free / premium / enterprise) — ch04 §"rate limit 사용 케이스" SaaS 차등이 가장 직관
- 매칭 포맷: Lyft envoy 중첩 descriptors — ch04 인용 포맷의 자연 확장, 트리 yaml로 정책 가시성 ↑
- 매칭 우선순위: **가장 구체적(depth 큰) 매치 우선** — Lyft envoy 동작 동일
- 핫리로드: watchdog 파일 watcher (vs SIGHUP/polling) — 즉시 반영, atomic swap
- user_tier 신뢰 모델: **학습용** 헤더 그대로, 실서비스는 API key DB resolution 필수
- watcher 함정 대비: vim/emacs atomic save(`tmp → rename`)는 `on_moved`도 핸들

**새 정책 분기** (cycle 4 적용 후):

| endpoint | user_tier | 정책 |
|---|---|---|
| shorten | free (default) | sliding_window_log, 분당 **10** |
| shorten | premium | sliding_window_log, 분당 **50** |
| shorten | enterprise | sliding_window_log, 분당 **500** |
| redirect | * | token_bucket, 50/s burst 100 (모든 사용자 동일 — 익명 IP라 tier 의미 약함) |

**테스트 시나리오와 결과**:

**Unit 5개 (다차원 매칭)**:
1. `test_endpoint_only_match`: user_tier 미선언 → endpoint default rule (10)
2. `test_endpoint_plus_tier_match`: `(endpoint=shorten, user_tier=premium)` → 50, enterprise → 500
3. `test_specificity_priority`: 입력 entries 순서 바꿔도 결과 동일 (depth 큰 매치)
4. `test_unknown_tier_fallback`: 미정의 tier → endpoint default
5. `test_unknown_endpoint_returns_none`: 없는 endpoint → None

**Unit 2개 (핫리로드)**:
1. `test_reload_picks_up_new_rule`: yaml 수정 → watcher trigger → lookup이 새 값 반환 (1.09초 내 완료)
2. `test_reload_failure_keeps_previous`: 잘못된 yaml 수정 → 이전 rules 유지 (atomic swap 안전성)

**Integration 3개 (e2e)**:
1. `test_free_tier_limited_at_10`: `X-User-Tier: free` 11회 → 11번째 429
2. `test_premium_tier_limited_at_50`: premium 51회 → 51번째 429
3. `test_default_tier_uses_endpoint_default`: tier 헤더 없이 11회 → 11번째 429

→ 헤더 하나로 정책 분기가 작동. yaml 1줄 수정으로 즉시 반영 가능 (~100ms).

## 5. 누적 테스트 결과 (cycle 0~4)

| Cycle | Unit | Integration | 누적 | 신규 검증 명제 |
|---|---:|---:|---:|---|
| 0 | 6 | 4 | 10 | 인프라 흐름 |
| 1 | +5 | +3 | 18 | "Lua atomic" (101/200) + "버스트 허용" (58% pass) |
| 2 | +3 | 0 | 21 | "경계 burst 2배" (200/2401 pass with double spike) |
| 3 | +4 | +3 | 28 | "boundary burst 부재" (55% smooth, no spike) + 0 jitter race |
| 4 | +7 | +3 | **38** | 다차원 매칭 + 핫리로드 (yaml 수정 → 100ms 반영) |

알고리즘 코드는 cycle 4에서 한 줄도 안 바뀌었지만 정책 표현력이 극적으로 확장됨 — plug-in 추상화의 가치 검증.

## 6. ch04 비교표 진행 상황

ch04 §"알고리즘 비교" 표 5개 셀 중 **3개가 그래프 증명 완료**:

| 알고리즘 | 정확도 | 메모리 | 버스트 | 우리 그래프 |
|---|---|---|---|---|
| token_bucket (cycle 1) | 중 | 적음 | **허용** | burst 시나리오 58% pass = capacity 100 흡수 |
| fixed_window (cycle 2) | **낮음** | 적음 | — | 분 경계 spike-deny-spike (200/12s) |
| sliding_window_log (cycle 3) | **높음** | **많음** | — | boundary_burst_replay 균등 throttle (no spike) |
| leaking_bucket | 중 | 적음 | 평탄화 | cycle 7 회고 글 (스킵 — token bucket의 거울) |
| sliding_window_counter | 중·근사 | 적음 | 평탄화 | cycle 7 회고 글 (스킵 — sliding log의 근사) |

스킵된 2개는 양 극단(token bucket, sliding log)을 잡고 있으므로 사이의 알고리즘은 글만으로 위치 추정 가능. 회고 페이지에서 메모리 트레이드오프 + 실세계 사용처 정리 예정.

## 7. ch04에 없는 실전 사실 (학습 노트 누적)

ch04는 알고리즘 본질만 다루고 production 라이브러리·운영 환경 디테일은 안 다룸. 직접 구현해야만 발견 가능한 함정 6개를 발견·기록:

1. **`fakeredis`의 Lua 지원 = `lupa` 패키지 필요** (cycle 1)
2. **redis-py `Script` 객체의 stale client binding** — 등록 시점의 클라이언트 참조 잡음, 클라이언트 교체 시 재등록 필요 (cycle 1)
3. **`httpx.ASGITransport`는 `request.client.host` 공통** — 테스트마다 식별자 명시 격리 필수 (cycle 1)
4. **로컬 포트 8000 충돌** (cycle 2)
5. **pandas `dt.floor("S")` deprecated** → `"s"` (cycle 2)
6. **`df.to_markdown()` ↔ `tabulate` 의존성** (cycle 2)

추가로 cycle 4에서 **watchdog의 vim/emacs atomic save 패턴**(`tmp → rename` → `on_moved`)을 미리 인지하여 함정 0건.

## 8. 책에 충실한 부분 vs 우리가 확장한 부분

**책 충실**:
- 알고리즘 본질 (token bucket refill/cap, fixed window slot, sliding log ZSET, 비교표)
- 응답 헤더 표준 (`X-Ratelimit-Limit/Remaining/Retry-After`, 429)
- Lyft envoy yaml 포맷
- "락 안 쓴다, Lua atomic" 원칙
- Redis 단일 저장소

**책에서 확장**:
- ZSET member 형식 (`ts_us-random_hex_4`) — 책의 묵시 가정 보강
- Race condition 실측 (101/200 vs 0 jitter) — 책은 그림만
- Boundary burst 직접 그래프 — 책은 글로만
- 다차원 매칭의 specificity 우선 — Lyft 동작 추가 명시
- Hot reload (watchdog) — 책은 "워커가 로드"만 언급, 실제 메커니즘 X
- `mode: soft` throttle (cycle 5) — 책의 한 단락("hard vs soft")의 구체 구현
- `MAX_THROTTLE_MS` 안전 장치

**의도적으로 안 한 부분** (회고에서 정리):
- 멀티 DC eventual consistency
- OSI L3 차단 (iptables 등)
- Edge 분산 배치 (Cloudflare 194 edge 같은)
- leaking_bucket / sliding_window_counter 풀 구현

## 9. 다음 단계 (cycle 5~7)

### Cycle 5 — Hard vs Soft 정책 (진행 중)

cycle 0의 `Rule.mode` 필드 활성화. premium tier만 soft (한도 초과 시 throttle 후 200), 나머지는 hard. 알고리즘 코드 0줄 변경. `MAX_THROTTLE_MS=2000` 초과 시 hard fallback (장기 폭주 보호).

### Cycle 6 — 클라이언트 SDK

서버가 만든 `Retry-After` + `X-Ratelimit-Throttled` 헤더를 클라이언트가 어떻게 처리하나. exponential backoff 패턴 직접 구현해서 naive httpx 클라이언트와 부하 시험 비교.

### Cycle 7 — 회고

- 스킵된 알고리즘 2개 (leaking_bucket, sliding_window_counter) — wiki 글로 정리. 메모리 트레이드오프 + 실세계 어디서 쓰나 (Shopify, Cloudflare 실측)
- ch04 후반 토픽 (multi-DC, OSI L3, edge 배치) — 왜 스코프 외였나, 어디서 다뤄지나 (ch05/06/08)
- Cross-link: 모든 알고리즘 wiki 페이지의 "등장 사례"에 본 실험 추가, knot 4 차트를 한 그래프로 비교

---

## 부록 — 본 문서와 다른 자료의 관계

| 무엇이 | 어디 | 무엇을 다루나 |
|---|---|---|
| 본 문서 (DESIGN.md) | `experiments/knot/` | **설계 narrative + ch04 매핑 + 테스트 시나리오·결과** (코드 무) |
| README.md | `experiments/knot/` | 빠른 시작·디렉터리·설치법 |
| wiki/projects/knot.md | `wiki/` (옵시디언 그래프 포함) | **task별** 진행 기록 + 함정 + 결정 사유. 시간순 다이어리 |
| docs/specs/...-design.md | `docs/specs/` | 사이클별 sub-spec (시스템 설계 결정 표) |
| docs/plans/... | `docs/plans/` | 사이클별 TDD 구현 계획 (코드 포함) |
| log.md | repo root | 한 줄짜리 활동 로그 |

본 문서는 1~2년 후 다시 폈을 때 "왜 이렇게 만들었나, 어떻게 검증했나"가 자족적으로 보이도록 작성. 사이클 6~7 완료 시 동일 형식으로 append 예정.
