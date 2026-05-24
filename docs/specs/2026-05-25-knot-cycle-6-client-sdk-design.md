# knot Cycle 6 — 클라이언트 SDK 미니 설계

- **문서 종류**: Sub-spec (cycle 6, full)
- **상위 spec**: `docs/specs/2026-05-24-rate-limiter-design.md`
- **작성일**: 2026-05-25
- **관련 위키**: [[rate-limiting]] (§"클라이언트 모범 사례"), [[ch04-rate-limiter]]
- **상태**: 작성 직후

## 0. 목적과 학습 의도

[[ch04-rate-limiter]] §"클라이언트 모범 사례"는 4가지 권고를 한 단락에 나열:

1. **응답 캐시** — 같은 요청 중복 호출 방지
2. **한도 인지** — 응답 헤더로 남은 횟수 추적·표시
3. **우아한 429 처리** — 거부 시 사용자 친화적 메시지
4. **Exponential backoff** — 재시도 시 지수적 간격 증가

cycle 6은 **이 4가지를 직접 구현한 SDK와 naive 클라이언트를 같은 부하로 비교** — "클라이언트 측 대응이 있고 없고가 무엇을 바꾸나"를 정량으로 확인.

### 학습 목표

- 서버 측 rate limiter(cycle 0~5)와 **클라이언트 측 대응의 상보 관계** 시연
- 같은 부하를 두 클라이언트로 돌렸을 때 서버 호출 수·성공률·총 소요 시간의 차이 측정
- cycle 5에서 만든 `X-Ratelimit-Throttled` 헤더의 실제 활용 — SDK가 backoff 신호로 사용

## 1. 두 클라이언트의 정의

### 1-1. `NaiveClient` — baseline

```
httpx wrapper. 헤더·캐시·backoff 무지.
요청 보내고 응답 그대로 반환. 429 받으면 예외 발생, 거기서 끝.
```

목적: **클라이언트 측 대응이 없을 때** 무엇이 일어나는지 baseline. 비교 기준선.

### 1-2. `KnotClient` — 4가지 권고 적용 SDK

```
같은 httpx wrapper지만:
  - URL → response 5분 TTL 캐시
  - 응답 헤더 추적 (X-Ratelimit-Remaining 등)
  - 429 시 Retry-After 존중 + exponential backoff
  - 200 + X-Ratelimit-Throttled 시 자동 backoff (다음 요청 늦춤)
```

목적: **책의 4가지 권고를 코드로 실현**.

## 2. SDK 4가지 권고 구현 디테일

### 2-1. 응답 캐시 (권고 ①)

```python
# 의사코드
_cache: dict[str, (response, expires_at)] = {}
TTL = 5 * 60   # 5분

async def shorten(url):
    if url in _cache and now() < _cache[url][1]:
        return _cache[url][0]   # 캐시 히트, 서버 호출 X
    response = await _http.post("/shorten", json={"url": url})
    _cache[url] = (response, now() + TTL)
    return response
```

**왜 in-memory dict?** 학습용 + 단일 프로세스. 실서비스는 Redis/Memcached. 책도 형태는 언급 안 함 (응답 캐시 권고만).

**왜 5분 TTL?** 임의값. URL이 단축된 후 짧은 시간 안에 또 단축하려는 패턴이 흔함 (사용자가 결과를 잃어버리거나 새로고침). 5분 후엔 가능성 낮음. 실서비스라면 `Cache-Control` 헤더 존중.

### 2-2. 한도 인지 (권고 ②)

```python
# 매 응답마다 헤더 파싱
self.limit = int(response.headers.get("X-Ratelimit-Limit", 0))
self.remaining = int(response.headers.get("X-Ratelimit-Remaining", 0))
self.throttled = response.headers.get("X-Ratelimit-Throttled") == "true"
```

SDK 사용자는 `client.remaining` 같은 속성으로 자기 한도 상태 확인 가능. UI에 "오늘 남은 횟수 N" 표시 같은 용도.

### 2-3. 우아한 429 처리 (권고 ③)

429 받으면 예외 발생시키지 말고 **명시적 결과 객체로**:

```python
class RateLimitedResult:
    allowed: bool                    # 항상 False (429이므로)
    retry_after: float
    scope: str | None                # 어느 한도에 걸렸나 (지금은 unknown)
    raw_response: Response

async def shorten(url) -> ShortenResult | RateLimitedResult:
    ...
```

SDK 사용자는 `if isinstance(result, RateLimitedResult): show_message(...)` 패턴. 예외 처리보다 명확.

대안: 예외(`RateLimitError`). 우리는 명시적 결과 객체 선택 — 함수형, 타입 안전.

### 2-4. Exponential backoff (권고 ④)

429 받으면 자동 재시도. `Retry-After` 헤더가 있으면 그 값 사용, 없으면 지수 증가:

```
attempt 1: 즉시 시도
attempt 2: Retry-After or 1s
attempt 3: Retry-After or 2s
attempt 4: Retry-After or 4s
... cap = MAX_BACKOFF_S
```

**`X-Ratelimit-Throttled: true` 응답 (cycle 5)** 받으면 **다음 요청 보내기 전 자동 대기**. 200이지만 한도 hit이라는 signal — 미리 자제.

```python
if response.headers.get("X-Ratelimit-Throttled") == "true":
    self._next_request_delay = self._throttle_ms / 1000   # 다음 호출 시 대기
```

**Backoff 파라미터**:
- `MAX_ATTEMPTS = 4` — 4번 시도 후 RateLimitedResult 반환 (포기)
- `MAX_BACKOFF_S = 60` — 단일 wait 상한 (장기 폭주 방지)
- `BASE_S = 1`, factor 2 — `1, 2, 4, 8s` 진행
- `Retry-After` 헤더 우선 (서버가 정확히 알려준 값)

## 3. 비교 부하 시험 (Q3: C — 두 시나리오 분리)

`scripts/compare_clients.py` — 두 시나리오를 SDK·naive로 각각 돌리고 통계 출력.

### 시나리오 A: 캐시 효과 — 같은 URL 100번 반복

```
모든 100 요청이 같은 URL을 shorten
정책: shorten free = 10/min (cycle 4 default)
```

| 지표 | naive 예상 | SDK 예상 |
|---|---|---|
| 서버 호출 수 | 100 | **1** (첫 호출만, 이후 캐시 히트) |
| 성공 | 10 | **100** (캐시 히트는 한도 안 봄) |
| 429 | 90 | 0 |
| 총 소요 시간 | 10초+(429 폭주) | <1초 |

**책의 권고 ① 효과 — 99% 서버 부하 감소, 사용자 100% 성공**.

### 시나리오 B: backoff 효과 — premium 60번 균등 호출

```
60 요청, premium tier (50/min soft + MAX_THROTTLE_MS 2s 폴백)
1분 동안 1초마다 1개씩 보냄
```

cycle 5에서 본 것처럼 빠른 burst는 hard 429 폴백, 천천히 보내야 soft throttle 발동.

| 지표 | naive 예상 | SDK 예상 |
|---|---|---|
| 서버 호출 수 | 60 | 60 + backoff 재시도 |
| 성공 (200) | ~50 (51번째 429) | **~60** (Retry-After backoff로 모두 결국 성공) |
| 429 (포기) | ~10 | ~0 |
| Throttled 헤더 처리 | 무시 | 다음 호출 자동 늦춤 |
| 총 소요 시간 | 60초 + 폭주 | 60s ~ 80s (backoff 추가) |

**책의 권고 ④ 효과 — 같은 부하에 클라이언트가 끈질기게 재시도해서 결국 모두 성공**.

### 결과 산출

```
scripts/compare_clients.py --scenario cache_effect
scripts/compare_clients.py --scenario backoff_effect
```

각각 stdout에 표 + JSON 저장. 두 결과를 모아 `reports/client_comparison.md` 작성.

## 4. 테스트 전략

### Unit (`tests/unit/test_knot_client.py`) 5개

mock httpx 응답으로 클라이언트 로직 격리:

1. `test_naive_shorten_returns_response` — baseline 동작
2. `test_sdk_cache_hit_skips_server` — 같은 URL 두 번 호출 시 서버 1번만
3. `test_sdk_cache_expires_after_ttl` — `freezegun`으로 5분 지난 후 캐시 무효
4. `test_sdk_backoff_on_429` — 첫 응답 429 → backoff 후 200, 정상 결과 반환
5. `test_sdk_throttle_header_delays_next_request` — 200 + Throttled 받으면 다음 호출 전 대기

mock httpx: `respx` 라이브러리 (httpx에 mounting 가능한 mock).

### Integration — 안 함

비교 부하 시험 자체가 e2e 시연. 별도 integration 테스트 없음.

## 5. 디렉터리 구조

```
신규:
  experiments/knot/client/__init__.py
  experiments/knot/client/base.py             # 공통 — httpx wrapper
  experiments/knot/client/naive.py            # NaiveClient
  experiments/knot/client/sdk.py              # KnotClient (4 권고 적용)
  experiments/knot/scripts/compare_clients.py
  experiments/knot/tests/unit/test_knot_client.py
  experiments/knot/reports/client_comparison.md (+ JSON, 차트는 옵션)

변경:
  experiments/knot/pyproject.toml             # respx dev dep
  wiki/projects/knot.md                       # ## Cycle 6 섹션
  docs/specs/2026-05-24-rate-limiter-design.md  # §7 cycle 6 status
  log.md
```

`experiments/knot/client/`는 클라이언트 SDK 패키지. 실서비스라면 `pip install knot-client` 같은 PyPI 패키지가 될 위치.

## 6. 결정 이력 (Decision Log)

| # | 결정 | 선택 | 이유 |
|---|---|---|---|
| 1 | 클라이언트 형태 | async (httpx.AsyncClient) | knot 앱이 async, 동기 wrapper는 자명한 추가라 생략. 단순화 |
| 2 | 캐시 정책 | URL → response 5분 TTL in-memory dict | 책 권고 ① 가장 단순 형태. mock 서비스에 적합 |
| 3 | 429 처리 형태 | 명시적 결과 객체 (`RateLimitedResult`) | 예외보다 함수형·타입 안전. SDK 사용자가 분기 명확히 |
| 4 | Backoff 파라미터 | base=1s, factor=2, max=60s, attempts=4 | 표준 (AWS SDK 등). `Retry-After` 헤더 우선 |
| 5 | Throttled 헤더 처리 | 다음 호출 전 자동 대기 | cycle 5에서 만든 헤더 활용 — 200이지만 한도 hit signal |
| 6 | 비교 시나리오 | A(캐시 100회 반복) + B(backoff premium 60회) 분리 | 두 권고 효과를 격리 시연. 합치면 메시지 흐려짐 |
| 7 | mock httpx | `respx` 라이브러리 | httpx 공식 ecosystem, mount 패턴이 자연스러움 |
| 8 | 비교 부하 도구 | Python 스크립트 (k6 아님) | 클라이언트 상태(캐시·backoff)가 핵심이라 k6보다 Python이 적합 |
| 9 | Integration 테스트 | 없음 | 비교 부하 시험이 e2e 역할 |
| 10 | 응답 객체 타입 | dataclass (`ShortenResult`, `RateLimitedResult`) | 타입 안전, 사용자가 IDE 자동완성으로 필드 확인 |

## 7. 미해결 / 후속

- **분산 캐시**: 다중 노드에서 SDK 인스턴스 간 캐시 공유는 못 함. 실서비스라면 Redis 클라이언트 캐시. 학습 범위 외
- **인증·OAuth**: API key는 헤더 1개로 끝. 토큰 갱신·OAuth flow 등은 본 사이클 외
- **회로 차단기 (Circuit Breaker)**: 연속 실패 시 일정 시간 차단. ch04 본문 외, 회고에 잠깐 언급 가능
- **메트릭 출력**: SDK가 자체 통계(캐시 히트율 등) 수집·노출은 안 함. 실서비스 라이브러리는 보통 prometheus exporter 포함
