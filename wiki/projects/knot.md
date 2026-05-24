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

**사이클 로드맵 (요약)** — 2026-05-24 갱신: 원안 9 사이클 → 7 사이클로 단축. knot 엔드포인트가 실제 쓰는 알고리즘만 full cycle, 그 외는 demo lite 또는 회고에서 글로 정리. 자세한 배경은 spec §7 참조.

| # | 사이클 | 다루는 ch04 개념 | 형태 |
|---|---|---|---|
| 0 | Foundation | API gateway 위치, 응답 헤더 표준 | full ✓ |
| 1 | [[token-bucket-algorithm]] (redirect) | 버스트 허용 | full ✓ |
| 2 | [[fixed-window-counter-algorithm]] (demo) | 단순·**경계 burst 한계 시연** | demo lite |
| 3 | [[sliding-window-log-algorithm]] (shorten) | sorted set, race condition·Lua | full |
| 4 | 다차원 규칙 + 핫리로드 | 분산 동기화, rules-as-data | full |
| 5 | hard vs soft | 정책 강도 | full |
| 6 | 클라이언트 SDK | 429·Retry-After·exponential backoff | full |
| 7 | 회고 — [[leaking-bucket-algorithm]] / [[sliding-window-counter-algorithm]] 스킵 배경 + multi-DC·OSI L3·edge 배치 | 안 한 것 정리 | 회고 |

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

| ch04 요구사항             | Registry가 푸는 방식                        |
| --------------------- | -------------------------------------- |
| 엔드포인트별 다른 알고리즘        | `rule.algorithm` 문자열 → `get_limiter()` |
| 새 알고리즘 추가 (사이클 1~5)   | `_LIMITERS` dict에 1줄 추가                |
| Unknown algorithm 방어  | `KeyError` 명시적 throw — 잘못된 yaml 즉시 발견  |
| Stateful 알고리즘의 카운터 공유 | 싱글톤 인스턴스 (모듈 로드 시 1회)                  |

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

## Cycle 1 — Token Bucket

**목표**: [[token-bucket-algorithm]]을 plug-in으로 끼우고 k6 부하 실측으로 ch04 비교표의 "버스트 허용" 시그니처를 시각화. 동시에 k6+matplotlib 리포트 도구 chain을 1회 셋업해 cycle 2~5가 가볍게 굴러가게 만든다.

**산출**: 9 task, 8개 commit, 18개 테스트 통과 (unit 11 + integration 7). race demo로 Lua atomicity 직접 증명. 실측 그래프로 token bucket 3가지 시그니처(burst 흡수·평균 속도 제한·refill 회복) 모두 확인.

**Sub-spec**: `docs/specs/2026-05-24-knot-cycle-1-token-bucket-design.md` — 결정 이력 12개 표로 명시.

### Task 1 — Lua script + dev 의존성

**Commit**: `d51cee1`
**파일**: `app/limiter/scripts/token_bucket.lua` (32줄), `pyproject.toml`에 `freezegun`·`pandas`·`matplotlib`

[[ch04-rate-limiter]] §"race condition"의 두 가지 표준 해법 중 **첫 번째(Lua script)를 코드로 박는** 작업. Lua 자체가 한 덩어리(32줄)로 묶여 Redis가 단일 indivisible 연산으로 실행 → race 발생 불가.

핵심 4단계가 ch04 개념과 1:1 대응:

```lua
-- 1) 시각: ch04 §"분산 환경 - Synchronization"의 중앙화
local now = redis.call('TIME')

-- 2) 리필: ch04 token bucket 의사코드의 핵심 한 줄
tokens = math.min(capacity, tokens + elapsed * rate)
--                ^^^^^^^^ capacity cap (over-fill 방지)

-- 3) 차감: ch04 "토큰 있으면 통과, 없으면 거부"
if tokens >= cost then tokens = tokens - cost; allowed = 1
else retry_after = math.ceil((cost - tokens) / rate * 1000) end

-- 4) 저장 + TTL: ch04 §"성능과 운영"의 메모리 회수 패턴
redis.call('HMSET', ...); redis.call('EXPIRE', ...)
```

**자료구조 결정**: HASH (tokens, last_refill). 두 필드를 한 명령(`HMGET`/`HMSET`)으로 묶음 → Lua 짧아짐. 별도 키 2개로 분리해도 atomic은 보장되지만 코드 길어짐.

**TTL 결정**: `ceil(capacity / rate * 2)`. 풀 회복 시간의 2배 동안 비활성이면 메모리 회수. capacity=100, rate=50/s면 4초.

### Task 2 — TokenBucket 클래스 (TDD) — 함정 발견 1

**Commit**: `fcf5a73`
**파일**: `app/limiter/token_bucket.py`, `tests/unit/test_token_bucket.py` (5개)

5개 unit이 ch04 비교표 셀들을 직접 증명:
- `test_burst_absorbs_capacity_then_denies` → "**버스트: 허용**" 셀
- `test_refill_after_time_advance` → 시간 경과에 따른 토큰 회복 (book 의사코드)
- `test_overfill_capped_at_capacity` → `math.min(capacity, ...)` cap의 정확성 (1시간 비활성 후도 capacity까지만)
- `test_identities_have_separate_buckets` → ch04 §"식별자" — 사용자별 독립 bucket

**함정 1: `fakeredis`의 Lua 지원은 `lupa` 패키지가 있어야 활성화됨**

첫 실행: `redis.exceptions.ResponseError: unknown command 'evalsha'`. 원인: fakeredis가 `lupa`(Python Lua runtime)를 optional 백엔드로 사용. `fakeredis[lua]` extra = `lupa`. `uv add --dev lupa`로 해결.

**관찰**: lupa가 있으면 **freezegun이 fakeredis Lua 내부 `redis.call('TIME')`도 가로챔**. plan이 걱정한 monkeypatch나 fallback 필요 없음. **cycle 4 sliding window log도 같은 함정 가능성** — 그때 즉시 알아챌 수 있도록 본 노트에 기록.

### Task 3 — Registry 등록 + rules.yaml 전환 + e2e 갱신

**Commit**: `afc38e5`

**diff 크기 (사이클 0 설계가 실증되는 task)**:
- `registry.py`: 1줄 추가 (`"token_bucket": TokenBucket()`)
- `rules.yaml`: redirect 한 블록만 변경 (algorithm + burst)
- `test_middleware_e2e.py`: 1개 테스트 기대값 갱신 (50/50 → 100/99)

사이클 0에서 "그렇게 설계했다"고 주장한 plug-in 추상화가 cycle 1에서 **3줄짜리 변경으로 token bucket 활성화**가 가능함의 실증. cycle 2~5도 동일하게 3줄.

**`X-Ratelimit-Limit` 헤더가 알고리즘에 따라 자연 변경**:

| 알고리즘 | `Limit` 값 | 의미 |
|---|---|---|
| always_allow | 50 | `requests_per_unit` |
| token_bucket | **100** | `burst` = capacity |

같은 헤더, 다른 의미. **클라이언트 SDK는 알고리즘 모르고 헤더만 본다** — ch04의 "표준 응답 헤더가 추상화 경계" 원칙.

**사이클별 변경 1개 원칙**: `shorten`은 `always_allow` 유지. cycle 4(sliding window log)에서 변경 예정. 학습 단위·diff·PR 리뷰를 작게.

### Task 4 — 통합 테스트 + race demo — 함정 발견 2·3, atomicity 증명

**Commit**: `61a226f`. 18/18 통과.

**핵심 측정 — race demo 결과**

`asyncio.gather`로 200 동시 요청 (capacity=100, rate=50/s):

```
passed: 101 / denied: 99
```

- +1은 dispatch 동안 ~20ms × 50tok/s = 1 토큰 리필
- **Lua atomic 아니었다면 200 모두 통과**했을 것

[[ch04-rate-limiter]] §"race condition"이 그림(Figure 4-14)으로만 보여준 시나리오가 **실측 숫자로 변환됨**. cycle 4에서 "비원자 sliding window log vs Lua sliding window log" 비교의 baseline.

**함정 2: redis-py `Script` 객체의 stale client binding**

```python
self._script = get_redis().register_script(SCRIPT)  # 클라이언트 X에 바인딩
# 테스트 lifespan이 close_redis() → 새 클라이언트 Y 생성
self._script(...)  # 여전히 죽은 X를 호출 → RuntimeError: Event loop is closed
```

plan이 걱정한 "register_script가 SHA를 캐시 안 함"의 **정반대 — over-cache**. `Script` 객체는 등록 시점의 클라이언트 참조를 잡음. 클라이언트 교체 시 stale.

수정 — 클라이언트 변경 감지 후 재등록:

```python
if self._script is None or self._script_client is not client:
    self._script = client.register_script(self._script_src)
    self._script_client = client
```

**의미**: ch04 본문은 알고리즘 본질만 다루고 production library 디테일은 안 다룸. 이런 함정은 **직접 구현해야만 발견 가능**한 학습 자산. cycle 4 sliding window log에서 같은 패턴 재발 시 즉시 알아챌 수 있음.

**함정 3: 테스트 격리 — `x-api-key`가 일관되지 않으면 bucket 공유**

`httpx.ASGITransport`는 모든 요청이 같은 `request.client.host`를 갖음. POST에만 `x-api-key`를 박고 GET에는 안 박으면 → 두 테스트가 같은 bucket key를 공유 → 첫 테스트가 bucket 비우면 두 번째는 시작도 못 함.

**ch04 매핑**: "**식별자가 정확해야 정책이 의미를 가진다**" (§"식별자")의 실증. 실서비스에서도 같은 IP를 NAT로 공유하는 두 사용자의 bucket이 충돌하는 게 정확히 이 문제. 그래서 API key가 우선 식별자.

### Task 5 — `scripts/report.py` (알고리즘 무관)

**Commit**: `9a5c7f8`
**파일**: `scripts/report.py` (k6 NDJSON → pandas → matplotlib PNG → 마크다운)

**알고리즘 무관 설계의 의미** — 스크립트가 알고리즘 로직을 전혀 모름. cycle 2~5에서 같은 스크립트가 leaking bucket·fixed window 등 모든 알고리즘 결과를 동일 형식으로 처리. ch04 비교표를 직접 만드는 도구.

ch04 §"성능과 운영"의 두 질문("알고리즘이 효과적인가" / "규칙이 적절한가")에 차트로 답하는 게 본 도구의 목적.

### Task 6 — k6 시나리오 3종

**Commit**: `c5f9918`
**파일**: `load/token_bucket.k6.js` — burst, ramp, steady_burst_cycle

**왜 이 3개**: token bucket의 시그니처(흡수·평균 제한·refill 회복)를 각각 격리. cycle 2~5에서 alg만 바꿔 같은 시나리오를 돌려 비교 차트 생성.

### Task 7 — k6 실행 + 리포트 — 그래프가 ch04 비교표를 증명

**Commits**: `206251d`, `740758d` (gitignore)
**파일**: `reports/token_bucket.md` + `reports/token_bucket_timeseries.png`

**실측 결과**

| scenario           | total | denied | pass_rate | p50    | p95    |
|--------------------|------:|-------:|----------:|-------:|-------:|
| **burst**          |   200 |     84 | **58%**   | 56ms   | 58ms   |
| **ramp** (0→100rps)| 2,999 |    651 | **78%**   | 3.2ms  | 5.7ms  |
| **steady_burst_cycle** | 900 |    0 | **100%**  | 3.1ms  | 4.7ms  |

**ch04 token bucket 시그니처 3가지가 모두 차트로 확인**:

1. **Burst 흡수 + 즉시 거부** — 0초 spike에서 capacity 100 + dispatch 동안 ~16 refill = ~116 통과, 나머지 84 거부. [[ch04-rate-limiter]] 비교표 "**버스트: 허용**" 셀의 그림 증명
2. **Ramp 중 토큰 소진** — 평균 rate 50/s 초과 지점부터 거부 비율 ↑. 비교표 "정확도: 중" — 평균은 정확히, 단기 burst는 허용
3. **Cycle 휴식의 refill 회복** — 5초 휴식이 50/s × 5s = 250 토큰 생성 → capacity 100으로 cap → 다음 burst를 100% 통과. token bucket 의사코드의 refill 로직 직접 확인

**함정 4-6 (T7 실행 중 발견·해결)**:

4. **포트 8000 충돌** — 로컬 "Lemonade App"이 점유. `--port 8001` + `BASE_URL` env 주입. 미들웨어가 host/port 무관임의 부수적 확인
5. **`pd.Series.dt.floor("S")` deprecated** — pandas 2.2+. 소문자 `"s"`로 수정
6. **`df.to_markdown()` 의존성** — `tabulate` 필요. `uv add --dev tabulate`

T7 commit에 함께 포함. cycle 2~5에서 즉시 동작.

### Cycle 1 회고 — 무엇을 배웠나

**ch04 본문에 없는 실전 사실 6가지**:

1. `fakeredis[lua]` extra = `lupa` 필요 (Task 2)
2. redis-py `Script`의 stale client binding (Task 4)
3. `httpx.ASGITransport`는 `request.client.host`가 공통 → API key로 명시 격리 필요 (Task 4)
4. 로컬 포트 8000 충돌 (Task 7)
5. pandas `floor("S")` → `"s"` (Task 7)
6. `to_markdown()` ↔ `tabulate` (Task 7)

ch04는 알고리즘 본질만 다루고 production 라이브러리·운영 환경의 함정은 안 다룸. 직접 구현하면서만 발견 가능. **본 노트의 핵심 학습 가치**.

**증명한 ch04 명제 (실측·코드로)**:

- "락은 답이 아니다. 원자 연산이 답" — race demo 200 동시 → 101 통과 (atomic O), Lua 없었으면 200 통과 (atomic X)
- token bucket "버스트 허용" 시그니처 — burst 시나리오 58% pass = capacity 흡수 후 거부
- 규칙은 데이터, 알고리즘은 코드 — yaml 1줄 + registry 1줄로 always_allow → token_bucket 전환

**다음 사이클 ([[leaking-bucket-algorithm]]) 예고**:

같은 3개 k6 시나리오를 leaking bucket에 돌리면 burst 시나리오의 통과율이 **token bucket보다 현저히 낮아질 것** (rate 50/s만 통과, 나머지 즉시 거부 또는 큐잉). 비교 차트가 생기면 ch04 비교표의 "**평탄화: ○**" 셀이 그림으로 증명됨. cycle 2부터는 `scripts/report.py`가 overlay 기능을 가질지(여러 알고리즘 한 차트) 결정 필요.

**결정 이력**: spec `docs/specs/2026-05-24-knot-cycle-1-token-bucket-design.md` §7 (12개 결정·이유).

## Cycle 2 — Fixed Window Counter (demo lite)

**목표**: [[fixed-window-counter-algorithm]]의 "경계 burst" 한계를 그래프로 시연. knot 엔드포인트 정책 변경 없음 (demo 목적).

**산출**: 4 task (cycle 1의 ~1/2), 3개 unit + boundary burst k6 1개 + reports/fixed_window.md.

**Sub-spec**: `docs/specs/2026-05-24-knot-cycle-2-fixed-window-design.md` (결정 이력 10개).

### 학습 목표 — ch04가 글로만 설명한 "경계 burst" 시각화

ch04 §"알고리즘 비교": fixed window의 정확도 = **"낮음 (경계 burst)"**. 한 줄에 적혀 있던 이 한계가 무엇인지 그래프로 확인.

**실측 (boundary burst k6 12s × 200rps)**:

| 구간 | 결과 |
|---|---|
| 전체 12초 | 2,401 요청 |
| 통과 | **200 (정확히 2 윈도우 × 100 한도)** |
| 거부 | 2,201 (91.67%) |
| pass_rate | 8.33% |

차트의 두 통과 spike:

- **11:33:53** 근방 — 첫 윈도우 한도 100 흡수
- **11:34:00** 직후 — 분 경계 통과, 새 윈도우 한도 다시 100 흡수
- 두 spike 사이 약 6초는 첫 윈도우 한도 소진 상태로 전량 거부, 두 번째 spike 이후 약 4초도 동일

결과: **약 7초 간격을 두고 분 경계 전·후 2초 구간에 200 통과**. 100req/minute의 의도된 정책이 분 경계를 끼는 2초 구간 동안 **최대 200 요청 통과**를 허용 — ch04 비교표 한 줄("정확도: 낮음")의 그래프 증명.

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

### 함정 7 (T3 실행 중 발견·해결)

7. **`scripts/report.py` pandas/matplotlib datetime bar 차트 충돌** — bucket index가 pandas datetime이면 bar chart가 `ValueError: Must supply freq for datetime value`로 터짐. bucket index를 `HH:MM:SS` 문자열로 변환 후 plot. 부수 효과로 x축 라벨 가독성도 향상. **cycle 1 token bucket 리포트에도 동일 수정 적용됨** — 알고리즘 무관 도구 chain 개선

### Cycle 2 회고 — demo lite의 가치

**full cycle의 ~1/2 시간**(4 task)에 ch04 비교표의 한 셀("정확도: 낮음 (경계 burst)")의 의미가 명확히 박힘. full cycle(통합 테스트·다양한 k6 시나리오·풀 wiki)을 안 한 결정은 옳았음 — 학습 본질은 그래프 한 장.

cycle 3 ([[sliding-window-log-algorithm]] full)가 이 한계의 해결책. 두 알고리즘의 차이를 이번 그래프 + cycle 3 그래프 나란히 비교 가능.

**스킵된 알고리즘에 대한 회고**는 cycle 7에서 본격적으로 (왜 [[leaking-bucket-algorithm]] / [[sliding-window-counter-algorithm]] 안 했나, 실세계 어디서 쓰나).

---

## Cycle 3 — Sliding Window Log

**목표**: [[sliding-window-log-algorithm]]을 `shorten` 엔드포인트에 끼우고, cycle 2 boundary burst를 sliding window가 해결함을 그래프로 비교 증명. knot 두 엔드포인트 모두 적절한 알고리즘 활성화 완료(shorten=swl, redirect=tb).

**산출**: 8 task, ZSET + Lua 3명령 atomic 묶음으로 race demo 0 jitter 증명, 4개 k6 시나리오로 cycle 2와 직접 비교.

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

### Task 4 — Race demo (ZSET + Lua) — **0 jitter**

**결과**: 50 동시 POST (limit=10):

```
passed: 10 / denied: 40
```

**cycle 1 token_bucket의 101 통과(+1 jitter)와 결정적 차이**. sliding window log는 timestamp 엄격 비교라 dispatch 동안 윈도우 밖으로 빠지는 timestamp가 없음 — limit 도달 시 정확히 deny. cycle 1의 `+1`은 dispatch ~20ms × 50tok/s = 1 토큰 리필이 원인이었는데, sliding window log는 그런 "회복" 메커니즘이 없어 더 엄격한 atomic 증명.

| 알고리즘 | 동시 N | limit | 통과 | jitter | 이유 |
|---|---|---|---|---|---|
| token_bucket (cycle 1) | 200 | 100 | 101 | **+1** | dispatch 동안 refill |
| sliding_window_log (cycle 3) | 50 | 10 | 10 | **0** | timestamp 엄격 비교, refill 없음 |

ch04 §"race condition"이 그림으로만 보여준 atomicity의 두 번째·더 엄격한 실측 증명.

### Task 5-6 — k6 4시나리오 + 리포트

**실측 결과** (`reports/sliding_window_log.md`):

| scenario | total | denied | pass_rate | p50 | p95 | 의미 |
|---|---:|---:|---:|---:|---:|---|
| burst | 20 | 0 | **100%** | — | — | VU별 분리 bucket (per-VU api-key) |
| ramp | 899 | 599 | **33.37%** | 3.5ms | 4.8ms | rate 초과 지점부터 throttle |
| steady_burst_cycle | 179 | 0 | **100%** | — | — | VU별 분리 bucket |
| **boundary_burst_replay** | 361 | 161 | **55.40%** | 3.4ms | 4.7ms | **cycle 2와 직접 비교 — spike 없음** |

**핵심 시각 증명 — `boundary_burst_replay` 차트 비교**:

| 알고리즘 | 차트 패턴 |
|---|---|
| **fixed_window (cycle 2)** | **2개 spike (각 100 통과)** — 7초 간격, 분 경계 끼는 2초 구간에 의도 2배 통과 |
| **sliding_window_log (cycle 3)** | **부드러운 녹색 ramp 1→17 pass/s**, quota 소진 후 solid red wall, 이후 재개 — 경계 spike 패턴 **부재** |

cycle 2의 "spike-deny-spike" vs cycle 3의 "ramp-wall-resume" 대비가 ch04 §"알고리즘 비교"의 "fixed window 정확도: 낮음 (경계 burst)" → "sliding window 정확도: 높음" 한 줄 차이를 **그래프로 즉시 증명**.

**per-VU api-key 결정의 실전 함의** — k6 시나리오에서 `x-api-key: k6-${__VU}` 패턴으로 각 VU가 자기 bucket을 갖게 했음. shorten limit=10/min이라 모든 VU가 한 bucket을 공유했다면 첫 10요청 후 시나리오 끝까지 100% 거부였을 것. burst·steady_burst_cycle이 100% pass인 이유 — VU 수가 limit 안에 들거나 VU별 quota가 시나리오 길이 동안 안 소진됨. **이 식별자 격리 트릭이 없으면 sliding 동작을 시각화 못 함** — ch04 §"식별자"가 강조한 "식별자가 정책 의미를 결정한다"의 부수적 실증.

### Cycle 3 회고 — 알고리즘 비교 완성, knot 운영 단계 진입

cycle 1 token_bucket + cycle 2 fixed_window + cycle 3 sliding_window_log = **ch04 비교표 5개 알고리즘 중 3개를 그래프로 증명**:

| 알고리즘 | 정확도 | 메모리 | 버스트 | 우리 차트 |
|---|---|---|---|---|
| token_bucket (cycle 1) | 중 | 적음 | 허용 | `reports/token_bucket.md` — burst 58% pass |
| fixed_window (cycle 2) | **낮음** | 적음 | — | `reports/fixed_window.md` — 분 경계 spike-spike |
| sliding_window_log (cycle 3) | **높음** | **많음** | — | `reports/sliding_window_log.md` — boundary replay 균등 ramp |

남은 2개([[leaking-bucket-algorithm]] / [[sliding-window-counter-algorithm]])는 cycle 7 회고에서 wiki 글로 정리 예정. token bucket(평탄화 안 함) + sliding window log(엄격, 메모리 비쌈)가 양 극단을 잡고 있어 사이 알고리즘은 글만으로 위치 추정 가능.

**knot 완성 — 알고리즘 사이클 종료**. shorten·redirect 모두 적절한 알고리즘 활성화. cycle 4부터는 알고리즘 추가 없음, **운영 측면 진화**: 다차원 규칙 + 핫리로드 → hard/soft → 클라이언트 SDK → 회고.
