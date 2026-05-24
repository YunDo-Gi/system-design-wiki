---
type: project
project: knot
sources: [ch04]
---

# knot — Rate Limiter 학습 프로젝트

> URL 단축 SaaS mock을 캐리어로, [[ch04-rate-limiter]]의 모든 핵심 개념과 추가 토픽을 직접 구현·검증하는 학습 프로젝트의 사이클별 기록.
>
> - **코드**: `experiments/knot/`
> - **설계 문서**: `docs/specs/2026-05-24-rate-limiter-design.md`
> - **구현 계획**: `docs/plans/2026-05-24-knot-cycle-0-foundation.md` (사이클 0)

## 개요

[[ch04-rate-limiter]]의 의사코드·트레이드오프·실측 수치를 손으로 재현해 학습 효과를 강화하는 게 1차 목적이다. 가상 서비스 **knot**(URL 단축 SaaS)을 베이스로 깔고, 사이클별로 알고리즘 1개씩 점진적으로 추가하면서 ch04의 모든 개념을 코드와 부하 실험으로 검증한다.

**사이클 로드맵 (요약)**

| # | 사이클 | 다루는 ch04 개념 |
|---|---|---|
| 0 | Foundation | API gateway 위치, 응답 헤더 표준 |
| 1 | [[token-bucket-algorithm]] | 버스트 허용 |
| 2 | [[leaking-bucket-algorithm]] | FIFO·평탄 outflow |
| 3 | [[fixed-window-counter-algorithm]] | 단순·경계 burst 시연 |
| 4 | [[sliding-window-log-algorithm]] | sorted set, race condition·Lua 데모 |
| 5 | [[sliding-window-counter-algorithm]] | 근사 트레이드오프 |
| 6 | 다차원 규칙 + 핫리로드 | 분산 동기화, rules-as-data |
| 7 | hard vs soft | 정책 강도 |
| 8 | 클라이언트 SDK | 429·Retry-After·exponential backoff |
| 9 | 회고 | multi-DC·OSI L3·edge 배치 (안 한 것 정리) |

**캐리어 서비스의 향후 진화** — 현재는 한 앱 안에 `POST /shorten`과 `GET /{code}` 두 mock 핸들러가 공존하지만, 실서비스에서는 두 경로의 부하 특성이 정반대라 거의 항상 분리한다. 이 분리는 [[ch05-consistent-hashing]] · [[ch06-design-key-value-store]] · ch07(unique ID) · ch08(URL Shortener)에서 다루는 주제다. 본 사이클은 미들웨어가 엔드포인트별로 다른 규칙·다른 알고리즘을 적용할 수 있게 설계해 ch08 시점에 양쪽 서비스로 이식 가능하게 했다.

---

## Cycle 0 — Foundation

**목표**: 알고리즘 모듈만 끼우면 동작하는 베이스 완성 — FastAPI 앱, 미들웨어 셸, 규칙 로더, [[redis]] docker-compose, AlwaysAllow dummy limiter, 표준 응답 헤더.

**산출**: 10개 task, 10개 단위/통합 테스트 통과 (unit 6 + integration 4), 9개 commit + schema 1개.

### Task 1 — 프로젝트 스캐폴딩

**Commit**: `50a57c8`
**파일**: `experiments/knot/pyproject.toml`, `docker-compose.yml`, `.python-version`, 디렉터리 골격, 최소 README.

**ch04와의 관계**: 직접 적용 없음. 인프라 셋업. 다만 docker-compose에 `redis:7-alpine`을 넣은 결정은 [[ch04-rate-limiter]]의 핵심 결정 "**카운터는 DB가 아니라 Redis에 둔다**" (ch04, p.69)를 위한 사전 준비다. `INCR`·`EXPIRE`·sorted set·Lua가 사이클 1+에서 이 Redis 위에서 돌아간다.

**기록 가치**: Python 3.12 + [[redis]] async client + FastAPI + pytest-asyncio. 패키지 매니저는 `uv` (lockfile 빠르고 가상환경 일관성).

### Task 2 — Limiter 타입 정의 (Rule, Decision, Protocol)

**Commit**: `b4b7f4f`
**파일**: `experiments/knot/app/limiter/base.py`

ch04의 두 가지 핵심 개념을 **코드 구조로 박는 작업**:

**1. `Limiter` Protocol — 알고리즘 plug-in 슬롯**

```python
class Limiter(Protocol):
    async def allow(self, key: str, rule: Rule) -> Decision: ...
```

[[ch04-rate-limiter]]의 "알고리즘 비교" 표는 5개 알고리즘이 **같은 입출력 인터페이스를 가지되 내부 메커니즘만 다르다**고 전제하고 비교한다. Protocol이 그 전제를 코드로 명문화. 사이클 1~5에서 [[token-bucket-algorithm]], [[leaking-bucket-algorithm]], [[fixed-window-counter-algorithm]], [[sliding-window-log-algorithm]], [[sliding-window-counter-algorithm]] 5개가 이 한 인터페이스에 hot-swap으로 갈아끼워진다.

**2. `Decision` 필드 = ch04 "클라이언트 응답 형식" 표준의 1:1 매핑**

| `Decision` 필드 | ch04 응답 헤더 (p.71) |
|---|---|
| `limit` | `X-Ratelimit-Limit` |
| `remaining` | `X-Ratelimit-Remaining` |
| `retry_after` | `X-Ratelimit-Retry-After` |
| `allowed` | 429 분기 |

알고리즘 내부가 무엇이든 클라이언트에게 노출되는 정보는 표준화. ch04 "drop 대신 표준 응답 헤더로 클라이언트에게 알려라"의 직접 구현.

**3. `Rule.mode = "hard"|"soft"`** — ch04 "추가 토픽 — Hard vs soft rate limiting"을 위한 자리. 사이클 7에서 활성화. 지금은 필드만 박아두고 모든 limiter는 mode를 무시.

**4. `Rule.burst`** — [[token-bucket-algorithm]]의 "버킷 용량"과 "리필 속도"가 분리되어 있다는 사실의 반영. `requests_per_unit`는 평균 속도, `burst`는 순간 최대치.

### Task 3 — AlwaysAllow limiter (TDD)

**Commit**: `ec2df15`
**파일**: `experiments/knot/app/limiter/always_allow.py`, `tests/unit/test_always_allow.py`

ch04 개념의 **"부정형(negative space)" 시연**. 모든 알고리즘이 무엇을 안 했을 때 어떻게 되는지를 보여주는 reference baseline.

| 무엇 | AlwaysAllow | ch04 정상 알고리즘 |
|---|---|---|
| 카운터 | 없음 | [[redis]] `INCR`/sorted set/Lua로 atomic 관리 |
| 윈도우 | 없음 | fixed/sliding window로 시간 분절 |
| 거부 | 절대 안 함 | 임계 초과 시 429 |
| race condition | 없음 (상태 X) | 원자 연산 필수 |
| `remaining` 헤더 | 항상 `limit`과 동일 | 실제 잔여 반영 |

**왜 필요한가**:

1. **인터페이스 검증** — `Limiter` Protocol·`Decision` 흐름이 미들웨어와 잘 연결되는지를 알고리즘 복잡도 없이 검증. 사이클 1에서 token bucket을 끼울 때 "인터페이스 문제"와 "알고리즘 버그"를 분리 디버깅 가능.
2. **미들웨어 단독 테스트의 baseline** — Task 8에서 미들웨어를 테스트할 때 limiter가 깨끗하게 통과시켜야 "미들웨어 자체가 헤더를 올바르게 박는지"만 검증할 수 있음.
3. **사고 실험** — rate limit이 없으면? = AlwaysAllow와 동일. [[ch04-rate-limiter]] "왜 처리율을 제한해야 하는가"(자원 고갈·비용·과부하)의 정확히 반대편. 사이클 1에서 token bucket을 켜는 순간 무엇이 달라지는지를 부하 시험으로 비교 가능.

### Task 4 — Limiter Registry

**Commit**: `ced771b`
**파일**: `experiments/knot/app/limiter/registry.py`

ch04 "알고리즘 비교" 표를 **코드로 실현하는 라우팅 레이어**.

ch04 핵심 메시지: "알고리즘 선택은 비즈니스 요구에 따라 달라진다". 한 시스템 안에서도 엔드포인트마다 요구가 다를 수 있음. `rules.yaml`이 이미 그렇게 되어 있음:

```yaml
- value: shorten   → algorithm: sliding_window_log  (엄격)
- value: redirect  → algorithm: token_bucket        (버스트 허용)
```

이 "이름 → 구현체" 매핑이 registry. ch04 "기본 아키텍처" yaml 규칙 블록(p.69)이 알고리즘 이름을 문자열로 지정하는데, 그 문자열이 실제 코드 객체로 연결되는 지점.

| ch04 요구사항 | Registry가 푸는 방식 |
|---|---|
| 엔드포인트별 다른 알고리즘 | `rule.algorithm` 문자열 → `get_limiter()` |
| 새 알고리즘 추가 (사이클 1~5) | `_LIMITERS` dict에 1줄 추가 |
| Unknown algorithm 방어 | `KeyError` 명시적 throw — 잘못된 yaml 즉시 발견 |
| Stateful 알고리즘의 카운터 공유 | 싱글톤 인스턴스 (모듈 로드 시 1회) |

**싱글톤이 중요한 이유** — ch04 "분산 환경의 난제 — Synchronization"과 직결. 요청마다 새 limiter 인스턴스를 만들면 in-process 상태가 매번 초기화됨. 싱글톤 → 인스턴스 공유 → 카운터는 [[redis]]로 → 분산 환경의 sticky session 안티패턴을 피하는 구조의 1단계.

### Task 5 — Rules 로더 + rules.yaml (TDD)

**Commit**: `c47cf96`
**파일**: `experiments/knot/app/rules.py`, `experiments/knot/rules.yaml`, `tests/unit/test_rules.py`

ch04 "기본 아키텍처"의 **Lyft 오픈소스 yaml 포맷(p.69) 그대로 구현**.

ch04 (p.69)와 우리 것을 나란히:

```yaml
# ch04
domain: messaging
descriptors:
  - key: message_type
    value: marketing
    rate_limit:
      unit: day
      requests_per_unit: 5
```

```yaml
# 우리 rules.yaml
domain: knot
descriptors:
  - key: endpoint
    value: shorten
    rate_limit:
      algorithm: always_allow
      unit: minute
      requests_per_unit: 10
```

스키마 1:1. `algorithm`/`burst`/`mode` 옵션 필드만 추가. 핵심 구조(`domain` × `descriptors`[`key`, `value`, `rate_limit`]) 동일.

| ch04 메시지 | 구현 |
|---|---|
| 규칙은 디스크에 yaml로 두고, 워커가 정기적으로 캐시로 로드 (p.69) | `load_rules()` 시작 시 1회 호출, `app.state.rules`에 캐시. 핫리로드는 사이클 6 |
| 규칙을 데이터로 외부화 — 코드 배포 없이 정책 변경 | yaml만 수정 후 reload |
| 다차원 키 (`message_type=marketing`, `user_tier=free` 조합) | `(key, value)` 튜플 인덱스. 사이클 6에서 복합 키로 확장 |

**`Rules.lookup() → Rule | None`** — ch04 "규칙 없음"의 경계 케이스 안전 장치. Task 8 미들웨어에서 `if rule is None: pass-through + warn` 패턴으로 활용. ch04 "잘못 구성된 규칙이 무차별 차단을 만든다"의 방어.

### Task 6 — Redis 클라이언트 싱글톤

**Commit**: `7be9ead`
**파일**: `experiments/knot/app/redis_client.py`

[[ch04-rate-limiter]] "기본 아키텍처"의 핵심 결정 "**카운터는 DB가 아니라 [[redis]]에 둔다**" (p.69)를 위한 클라이언트.

지금 시점엔 카운터를 아직 안 쓰지만 사이클 1+의 모든 알고리즘이 이 싱글톤 클라이언트를 공유한다. 작지만 ch04 두 토픽을 위한 사전 셋업:

**1. ch04 "분산 환경의 race condition" 해법의 전제**

ch04는 락이 아니라 원자 연산(Lua, sorted set)을 권한다. 그게 가능하려면 모든 요청이 같은 [[redis]] 연결 풀을 봐야 함. 싱글톤 + connection pool이 그 전제 조건. 요청마다 새 클라이언트면 connection 폭증 (atomic 보장은 그대로지만 자원 낭비).

**2. ch04 "분산 환경의 Synchronization" — 중앙 공유 저장소**

ch04: "여러 rate limiter 서버가 카운터를 각자 가지면 정책이 어긋난다 ... 표준은 중앙 공유 저장소." `REDIS_URL` 환경변수 → 모든 limiter 인스턴스(여러 앱 노드)가 같은 [[redis]] URL을 가리킴. 사이클 6에서 다중 노드 시연할 때 이 한 줄 환경변수만으로 노드 늘려도 카운터가 어긋나지 않음.

**구현 디테일**:
- `Redis.from_url`은 동기 호출이지만 반환값은 `redis.asyncio.Redis` — 실제 I/O는 await 시. lazy init이라 import 시점엔 연결 안 함 → 테스트가 [[redis]] 없이도 import 가능.
- `decode_responses=True` — bytes 대신 str 반환. Lua 결과나 카운터 값을 즉시 int/str로 다룰 수 있음 (사이클 4 sliding window log에서 timestamp 문자열 처리할 때 편함).

### Task 7 — FastAPI 앱 + mock `/shorten` `/{code}` + `/healthz`

**Commit**: `5f66cf2`
**파일**: `experiments/knot/app/main.py` (+ placeholder `app/middleware.py` — Task 8에서 본 구현으로 덮어씀)

세 가지 ch04 개념을 직접 구현:

**1. ch04 "위치/배치" — middleware 마운트 (p.59)**

```python
app = FastAPI(lifespan=lifespan)
app.add_middleware(RateLimitMiddleware)   # 모든 라우트 핸들러 앞단
```

ch04 표 마지막 행("[[api-gateway]] 미들웨어 — rate limit + SSL + auth + IP whitelist 묶음")의 in-process 버전. `add_middleware`로 모든 요청이 핸들러 도달 전에 미들웨어를 거침. ch08 시점에 Envoy로 옮기면 이 한 줄이 사라지고 Envoy config로 이동 — 패턴 동일.

**2. ch04 rules.yaml — 시작 시 로드 (p.69)**

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.rules = load_rules(RULES_PATH)
    yield
    await close_redis()
```

ch04 "규칙은 시작 시 캐시로 로드"의 단순한 구현. 핫리로드는 사이클 6.

**3. ch04 "성능과 운영 — 모니터링"의 사전 준비**

```python
@app.get("/healthz")
async def healthz():
    try:
        pong = await get_redis().ping()
        return {"status": "ok", "redis": "ok" if pong else "fail"}
    except Exception as e:
        return {"status": "degraded", "redis": f"error: {e}"}
```

[[redis]]가 죽으면 모든 limiter가 fail해야 하므로 가장 critical한 의존성. `/healthz`가 false면 사이클 1+에서 fail-open 정책 발동.

**4. URL 단축 mock (ch04와 무관)**

`POST /shorten` → `secrets.token_urlsafe(6)`로 코드 생성, `GET /{code}` → 302. 학습 목적상 mock으로 충분. ch07(unique ID generator), ch08(URL Shortener)에서 분산 ID 생성·[[consistent-hashing]] 등으로 교체될 자리.

### Task 8 — RateLimitMiddleware (TDD)

**Commit**: `7043d92`
**파일**: `experiments/knot/app/middleware.py` (본 구현), `tests/conftest.py`, `tests/integration/test_middleware_e2e.py`

ch04를 본격적으로 코드로 실현하는 task. 그리고 **두 개의 실제 엔지니어링 사실을 발견**:

**발견 1: Starlette `BaseHTTPMiddleware`는 라우팅 전에 실행됨**

`request.scope["route"]`는 미들웨어 시점에 `None`. → path 패턴 매칭으로 fallback. Starlette 아키텍처상 명시적 트레이드오프 — 미들웨어가 어떤 라우트로 갈지 모르기 때문에 경로 기반으로 결정. ch04 "위치/배치"에서 "[[api-gateway]] 미들웨어"가 보통 path 패턴 매칭을 쓰는 것과 정확히 같은 이유.

**발견 2: `httpx.ASGITransport`는 lifespan을 실행하지 않음** (spec/plan에 없던 함정, TDD가 잡음)

`ASGITransport`로 테스트 클라이언트를 만들면 FastAPI `lifespan`이 실행 안 됨 → `app.state.rules` 미설정 → 미들웨어가 조용히 "no rule → passthrough" 분기로 가서 헤더 주입 안 함. 직접 ASGI lifespan 프로토콜을 구현한 `LifespanContext`로 해결 (`tests/conftest.py`). **이게 없었다면 모든 테스트가 거짓 통과(false positive)**.

**ch04 매핑**

**a. "클라이언트 응답 형식" (p.71) — 응답 헤더 표준 직접 구현**

```python
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
```

- 429 + Retry-After + 두 X-Ratelimit-* 헤더 = ch04 표 1:1
- 거부뿐 아니라 정상 응답에도 헤더 주입 — ch04 강조점 ("클라이언트가 자기 한도를 항상 알 수 있어야")
- 사이클 8 클라이언트 SDK가 이 헤더들을 읽어서 [[rate-limiting]]의 exponential backoff 결정

**b. "기본 아키텍처" 흐름의 코드화**

```
client → middleware → [rule lookup → limiter.allow → decision] → handler
                                                          ↓
                                                       (deny) 429
```

Limiter는 미들웨어 안에 박혀 있지 않고 plug-in — registry로부터 동적 조회. 사이클 1+에서 알고리즘 교체 시 미들웨어 코드는 한 줄도 안 바뀜.

**c. "식별자" 결정**

```python
identity = request.headers.get("x-api-key") or (request.client.host if request.client else "unknown")
key = f"knot:{endpoint}:{identity}"
```

ch04 식별자 후보: API key, user ID, IP. 우리는 API key 우선, 없으면 IP — 인증된 사용자는 정확히, 익명도 IP 단위로 abuse 방어. ch04 "hard vs soft" 논의의 전제 조건.

**d. "규칙 없음" 안전 장치**

```python
if rule is None:
    logger.info("no rule for endpoint=%s — passing through", endpoint)
    return await call_next(request)
```

`/healthz`처럼 의도적으로 규칙 없는 엔드포인트가 영향받지 않음.

**e. "분산 환경 — Synchronization"의 1단계**

미들웨어가 in-process이고 stateless — 카운터를 자체 보유하지 않음. registry의 limiter도 stateless wrapper (실제 카운터는 사이클 1+에서 [[redis]]). 노드를 N개로 늘려도 정책이 어긋나지 않을 구조의 기반.

### Task 9 — `/healthz` 통합 테스트 (실제 Redis)

**Commit**: `b025a4c`
**파일**: `experiments/knot/tests/integration/test_healthz.py`

ch04 직접 개념 적용은 적고, **운영 인프라(observability)** 측면이 메인.

**1. ch04 "성능과 운영 — 모니터링" 토대**

ch04: "모니터링 ① 알고리즘 자체가 효과적인가 ② 규칙이 적절한가." 이걸 가능하게 하려면 먼저 **시스템이 살아 있는지부터** 알아야 함. `/healthz`가 1차 신호. `REDIS_AVAILABLE=1` 환경변수 가드로 strict/loose 모드 분기.

**2. ch04 "분산 환경 — 중앙 공유 저장소" 살아있음 신호**

[[redis]]가 죽으면 fail-open이든 fail-closed든 결정해야 하고, 그 결정은 모니터링 신호가 있어야 가능. 사이클 1+에서 카운터를 실제로 쓰기 시작하면 이 신호의 무게가 더 커짐.

**3. 사이클 0이 끝나는 신호 — 모든 부품이 연결되었다**

이 테스트 통과 = FastAPI 앱이 뜸 ✓ / lifespan이 실행되어 rules 로드 ✓ / 미들웨어가 마운트되어 `/healthz` 통과 분기를 정확히 탐 ✓ / [[redis]] 클라이언트가 실제 [[redis]]와 통신 ✓ / registry → AlwaysAllow → Decision → 헤더 흐름 정상 ✓.

사이클 1에서 `token_bucket.py` 한 파일 추가 + registry 1줄 등록 + yaml 1줄 변경 = 즉시 동작.

### Cycle 0 회고 — 무엇을 배웠나

**ch04 책 본문엔 없는 두 가지 실전 사실** (TDD가 발견):

1. **Starlette `BaseHTTPMiddleware`는 라우팅 전 실행**이라 endpoint를 path로 결정해야 함. ch04는 미들웨어 위치만 권하고 라우팅 시점 같은 framework-specific 사실은 안 다룸 — 직접 구현하면서야 잡힘.
2. **httpx `ASGITransport`는 lifespan 미실행** → 통합 테스트가 거짓 통과할 수 있음. 학습 프로젝트라도 통합 테스트가 false positive면 의미 없으니 직접 lifespan driver를 짜서 해결.

**구조 결정**: `Limiter` Protocol + Registry + Rules 로더의 3층 분리. 사이클 1~5에서 알고리즘 추가는 모듈 1개 + registry 1줄 + yaml 1줄 = 합쳐 3개 변경으로 끝나도록 격리. 이 격리가 다음 9개 사이클의 진행 속도를 결정한다.

**아직 안 한 ch04 토픽**: race condition·Lua·sorted set(사이클 4), hard/soft enforcement(사이클 7), 클라이언트 backoff(사이클 8), multi-DC·OSI L3·edge 배치(사이클 9 회고).

---

## Cycle 1 — Token Bucket (예정)

미작성. 사이클 1 시작 시 별도 spec/plan 작성 후 본 섹션 append.
