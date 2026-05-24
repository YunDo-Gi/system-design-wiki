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

## Cycle 4 — 다차원 규칙 + 핫리로드

**목표**: 알고리즘 변경 없이 **운영 측면** — Lyft envoy 중첩 descriptors로 user_tier 차등 정책 + watchdog 파일 watcher로 핫리로드.

**산출**: 7 task, 38개 테스트 통과 (이전 28 + multidim unit 5 + reload unit 2 + multidim e2e 3). 새 의존성 `watchdog`. 알고리즘 코드 0줄 변경.

**Sub-spec**: `docs/specs/2026-05-24-knot-cycle-4-multi-dim-rules-design.md` (결정 이력 12개).

### 무엇이 달라졌나

| | cycle 3까지 | cycle 4 |
|---|---|---|
| 매칭 차원 | `endpoint` 1개 | `endpoint` × `user_tier` 2개 |
| Rules 모델 | 평면 dict | **트리 (RuleNode)** + DFS 매칭 |
| 매칭 우선순위 | — | **가장 구체적 우선** (specificity) |
| 정책 변경 | 앱 재시작 필요 | **watchdog 핫리로드** — 즉시 반영 |
| `shorten` 정책 | 분당 10 (모든 사용자) | free 10 / premium 50 / enterprise 500 |
| `redirect` 정책 | 변경 없음 | 변경 없음 (익명 IP 식별자라 tier 의미 약함) |

### ch04 매핑 — 본 사이클의 핵심

**1. ch04 §"rules-as-data"의 본격 활용**

cycle 0에서 깐 Lyft 포맷이 사실은 **중첩 descriptors로 다차원 매칭을 표현**할 수 있음을 cycle 4에서 비로소 활용:

```yaml
descriptors:
  - key: endpoint
    value: shorten
    descriptors:                  # ← 중첩으로 2차원 표현
      - key: user_tier
        value: premium
        rate_limit: { requests_per_unit: 50 }
    rate_limit: { requests_per_unit: 10 }   # default fallback
```

ch04가 인용한 그 포맷의 정확한 확장. **트리 yaml로 정책 가시성 ↑** — "이 엔드포인트의 default + tier별 override" 구조가 한눈에.

**2. ch04 §"기본 아키텍처" — "워커가 정기적으로 캐시로 로드"의 진짜 구현**

cycle 0에서 "시작 시 1회 로드"만 했던 게 cycle 4에서 비로소 **변경 즉시 반영**으로 진화. yaml만 수정하고 저장하면 100ms 이내 새 정책 적용. 앱 재시작 없음.

**3. ch04 §"분산 환경 — 중앙 공유 저장소"의 정책 측면**

cycle 0~3은 카운터의 중앙화(Redis). cycle 4는 **정책의 중앙화의 첫 단계** — 같은 yaml 파일을 보는 모든 노드가 같은 정책 적용. 실서비스에선 etcd/Consul로 진화 (회고).

### 핵심 결정 (spec §6 일부)

- **차원 선택**: `user_tier` (vs client_type/region) — SaaS 차등이 ch04와 가장 직관
- **포맷**: Lyft envoy 중첩 descriptors (vs flat tuple) — 트리 가시성 + ch04 일관성
- **핫리로드**: watchdog 파일 watcher (vs SIGHUP/polling) — 즉시 반영
- **atomic swap**: 새 Rules 객체 통째 교체 — partial reload 함정 회피, 실패 시 이전 유지
- **user_tier 신뢰**: **학습용**은 헤더 그대로, 실서비스는 API key DB resolution 필수 (회고에 명시)

### 발견된 함정 (cycle 1~3 노트 누적의 가치 검증)

이번 사이클은 **새 함정 거의 없음** — 알고리즘 변경 안 했고 cycle 1~3 패턴(Lua, fakeredis lupa, stale Script, ASGI client.host) 재사용 0건 (rules.py·middleware.py 영역). 새로 만난 디테일:

- **watchdog 에디터 atomic save**: vim/emacs는 `tmp → rename`. `on_modified` 외 `on_moved`도 핸들 — Lyft 포맷 같은 yaml은 에디터 차이 크니까 미리 둘 다 처리
- **macOS FSEvents 지연**: 로컬 dev에선 ~50ms 즉시 반영, CI/Linux는 polling fallback도 옵션 (`watchdog.observers.polling`)

### Cycle 4 회고

knot은 이제 **알고리즘 + 정책 표현력**이 모두 작동:
- 알고리즘: token_bucket (redirect) + sliding_window_log (shorten)
- 정책: endpoint × user_tier × (default fallback) 다차원, 핫리로드

cycle 5는 **정책 강도** 차원 추가 — `mode: hard` vs `mode: soft`. 같은 규칙에 enforcement 모드를 토글, soft는 throttle(지연 응답)로 완화.

---

## Cycle 5 — Hard vs Soft 정책

**목표**: cycle 0부터 박혀있던 `Rule.mode` 필드 활성화. premium tier에 `mode: soft` 적용 → 한도 초과 시 거부 대신 **throttle 후 통과**.

**산출**: 4 task (운영 사이클로 간결), 44개 테스트 (이전 38 + middleware unit 3 + e2e 3). 알고리즘 코드 0줄 변경.

**Sub-spec**: `docs/specs/2026-05-24-knot-cycle-5-hard-soft-design.md` (결정 이력 10개).

### ch04 §"추가 토픽 — hard vs soft"의 한 단락을 코드로

ch04 본문은 한 단락만 다룸 — "hard = 절대 불가, soft = 단기 초과 허용". 우리 구현:

| | hard (cycle 4까지 모든 정책) | soft (cycle 5 premium만) |
|---|---|---|
| 한도 초과 시 | 즉시 **429** + `Retry-After` 헤더 | **throttle** (`asyncio.sleep`) 후 **200** + `X-Ratelimit-Throttled: true` |
| 카운터 | 변경 안 됨 (allow=False) | 변경 안 됨 (decision은 deny 그대로) |
| 클라이언트 인지 | 명백한 429 | 응답 지연으로 자연 backoff signal |
| 비즈니스 시그널 | 보호 우선 | UX 우선 |

**핵심 결정**: soft에서 throttle된 요청은 **counter에 추가하지 않음**. limiter.allow()가 deny를 반환했으므로 counter는 그대로. soft = "한도는 유지하되 거부 대신 지연으로 표현". 메모리 누수 없음.

### Throttle 안전 장치 — `MAX_THROTTLE_MS = 2000`

retry_after가 2초 초과 시 **hard로 폴백 (429)**. 이유: 장기 폭주 사용자가 서버 thread/connection을 무한 점유하는 것 방지. soft도 무제한이 아님.

### 실측 (T3 수동 시연)

**Scenario A — free tier (hard, 10/min sliding_window_log)**:

```
free 1~10: 200
free 11:   429
```

11번째 요청에서 즉시 429. ch04 cycle 3에서 검증한 sliding_window_log의 엄격 동작 그대로.

**Scenario B — premium tier (soft, 50/min sliding_window_log)**:

```
premium 1~50: 200, elapsed ~30ms (서버 RTT)
premium 51:   status=429 elapsed=31ms, x-ratelimit-retry-after: 56.724
```

**핵심 발견**: premium 51번째 요청은 **soft 분기로 가지 않고 hard fallback으로 429**. 이유 — fast burst (51 요청 / ~1초)로 윈도우 안의 모든 timestamp가 거의 "지금"이라 retry_after ≈ 57s ≫ MAX_THROTTLE_MS(2s). middleware가 "throttle이 너무 길면 hard 폴백" 분기를 탐.

**이것은 의도된 동작이고 spec §"MAX_THROTTLE_MS 안전 장치"의 직접 시연**:
- soft mode는 "정상 사용자가 한도에 부드럽게 닿을 때 UX 우선" 용도
- abuse 패턴(짧은 시간 폭주)은 **soft여도 hard로 강등** — 서버 자원 보호

### 그래서 soft throttle이 실제로 일어나는 조건은?

retry_after < 2초가 되려면 요청 패턴이 **윈도우 끝자락에서 천천히 한도에 닿아야** 함. 예:
- 50/minute 한도에서 50번째 요청을 윈도우 시작 후 58초 즈음에 보냄 → 51번째는 약 2초 후에 oldest timestamp가 윈도우 밖으로 → retry_after ≈ 2s 이내 → soft throttle 발동
- 또는 더 작은 윈도우(예: 50/second)에서 51번째 요청 → retry_after < 1s → 즉시 throttle

**T2 integration test의 우회**: 위와 같은 "느린 한도 도달" 시나리오를 결정적으로 재현하기 어려워서 `test_premium_tier_soft_throttle`은 **테스트 전용 정책 override**(`unit: second`, `requests_per_unit: 2`)로 retry_after를 MAX_THROTTLE_MS 안쪽으로 강제. 프로덕션 정책(50/min) 그대로면 fast burst가 항상 429로 떨어져 throttle 분기 검증 불가.

**T2 `test_premium_throttle_does_not_count` 재설계**: 원래는 "51·52번째 둘 다 throttle 받음 → counter 안 늘었음을 응답으로 증명"이었으나, **51번째 throttle 동안 sleep(throttle_ms)하는 사이 윈도우가 스크롤**되어 52번째 시점에 oldest timestamp가 윈도우 밖으로 나갈 수 있음. 즉 52번째는 정상 200(throttle 없이)일 수 있어 응답으로 counter 불변을 증명 못 함. 결국 **Redis ZSET을 직접 ZCARD로 검사**해서 throttle 전후 카운트가 동일함을 검증하는 방식으로 변경.

### Middleware 분기 흐름

```
decision = await limiter.allow(...)

if allowed: 정상 200 + headers
else:
    if mode == soft and retry_after_ms < MAX_THROTTLE_MS:
        sleep retry_after → 200 + Throttled header
    else:
        429 + Retry-After header   (hard, 또는 soft의 long-throttle fallback)
```

알고리즘 코드 0줄 변경, 모든 정책 표현력이 middleware의 mode 분기로 흡수. **Limiter Protocol·Decision 추상화의 가치 누적 검증**.

### Cycle 5 회고

knot의 정책 표현력 두 단계 완성:
- **표현 차원**: cycle 4 `endpoint × user_tier` 다차원 매칭
- **표현 강도**: cycle 5 `mode: hard | soft` 정책 강도 토글

**핵심 학습 — soft mode의 실전 의미 재정의**: 책(ch04)이 hard/soft를 "보호 vs UX" 이분법으로만 다뤘다면, 직접 구현해보니 "soft = UX 우선이되 abuse 보호는 MAX_THROTTLE_MS로 hard 폴백"이라는 **2단계 정책**임이 드러남. soft는 abuse를 봐주는 게 아니라 "정상 사용자의 자연스러운 한도 도달"에만 적용. 이건 단순 토글이 아니라 **타임스케일 기반의 정책 선택자** — 짧은 throttle은 backoff signal, 긴 throttle은 거부.

남은 cycle 6: **클라이언트 SDK 미니** — 우리가 만든 `X-Ratelimit-Throttled` 헤더와 `Retry-After`를 클라이언트가 어떻게 처리하나. exponential backoff 패턴 직접 구현해서 naive client와 비교.

cycle 7: 회고 — 안 한 것 정리 (leaking_bucket / sliding_window_counter / multi-DC / OSI L3 / edge 배치).

## Cycle 6 — 클라이언트 SDK 미니

**목표**: [[ch04-rate-limiter]] §"클라이언트 모범 사례" 4가지 권고(캐시·한도 인지·우아한 429·exponential backoff)를 SDK로 구현. naive 클라이언트와 같은 부하로 비교해 클라이언트 측 대응의 정량 효과 시연.

**산출**: 5 task, 49 tests (이전 44 + client unit 5). `experiments/knot/client/` 패키지 신규(base/naive/sdk), `scripts/compare_clients.py`, `reports/client_comparison.md`.

**Sub-spec**: `docs/specs/2026-05-25-knot-cycle-6-client-sdk-design.md` (결정 이력 10개).

### 4가지 권고 구현

| 권고 | 구현 |
|---|---|
| ① 응답 캐시 | URL → response 5분 TTL in-memory dict. 같은 URL 반복 요청을 서버에 보내지 않음 |
| ② 한도 인지 | 응답 헤더 추적 (`X-Ratelimit-Limit/Remaining/Throttled`)으로 클라이언트가 한도 상태를 항상 알고 있음 |
| ③ 우아한 429 | `RateLimitedResult` dataclass로 명시적 반환 (예외 X). 호출자가 분기 처리 용이 |
| ④ Exponential backoff | base=1s, factor=2, max=60s, 4 attempts. `Retry-After` 헤더가 있으면 우선 사용 |
| ⑤ Throttled 헤더 활용 (cycle 5 산출물) | 200 + `X-Ratelimit-Throttled: true` 받으면 `Throttle-Ms` 만큼 다음 호출 전 자동 대기. 서버의 soft throttle 신호를 클라이언트가 능동적으로 인지 |

### 비교 실측 결과

**시나리오 A — 캐시 효과 (같은 URL ×100, free tier 10/min)**

| metric | NaiveClient | KnotClient |
|---|---:|---:|
| successes | 10 | **100** |
| rate_limited | 90 | **0** |
| total_seconds | 0.17 | 0.0 |
| cache_hits | — | **99** |
| server_calls | (100) | **1** |

NaiveClient는 10번까지만 통과하고 나머지 90번은 429. KnotClient는 첫 1번만 서버에 가고 99번은 캐시 히트 — 같은 결과 100건 받으면서 서버 부하 99% 감소.

**시나리오 B — backoff 효과 (60 reqs @ 1초 간격, premium tier 50/min)**

| metric | NaiveClient | KnotClient |
|---|---:|---:|
| successes | 52 | **60** |
| rate_limited | 8 | **0** |
| throttled_responses | 1 | 0 |
| total_seconds | 62.02 | 70.09 |
| backoff_waits | — | **1** |
| server_calls | (60) | **61** |

60초 동안 1초 간격으로 분산해도 premium 50/min 한도에 ~51번째에서 도달. Naive는 52 통과 후 8회 429로 포기 (마지막 1회는 200 + Throttled 헤더만 받음). SDK는 429 받자마자 `Retry-After`(~8s) 동안 backoff_wait 1번 → 재시도 성공으로 **60/60 모두 통과**. 총 시간 8초 늘었지만 데이터 손실 0.

### 핵심 발견

**1. 캐시 효과는 dramatic** — 성공률 10% → 100%, 서버 호출 -99%. ch04 권고 ①(클라이언트 캐시)이 단순한 최적화가 아니라 **rate limiter 시스템 전체 부하를 결정**하는 가장 큰 레버임. 서버 측 알고리즘 5종 비교(cycle 1~3)보다 클라이언트 캐시 한 줄이 더 큰 효과.

**2. Backoff 효과는 작지만 명확** — 52/60 → 60/60 (성공률 87% → 100%). 1번의 `Retry-After` 존중 재시도로 데이터 손실 0. backoff가 "느려지는 대신 안 잃는다"의 정확한 시연. 서버가 cycle 5에서 표준 헤더(`Retry-After`, `Throttled`)를 정확히 emit하기 때문에 클라이언트가 이 결정을 결정적(deterministic)으로 내릴 수 있음 — **서버·클라이언트 contract의 가치**.

**3. PYTHONPATH 함정** — `scripts/compare_clients.py`는 `from client.naive import ...` / `from client.sdk import ...`로 client을 top-level package로 import. `uv run python scripts/compare_clients.py` 직접 실행 시 cwd를 sys.path에 자동 추가하지 않아서 `ModuleNotFoundError: No module named 'client'` 발생. `PYTHONPATH=. uv run python scripts/...`로 우회. 향후 스크립트는 `python -m scripts.compare_clients` 패턴이나 `pyproject.toml` 의 `[tool.uv]` 설정으로 더 깔끔하게 해결 가능. **노트**: T2 시점엔 import 검증만 했고, T3 실행 시점에 표면화. 스크립트가 패키지 import를 한다면 PYTHONPATH·entry point 둘 다 사전 검증 필요.

### Cycle 6 회고

knot **operating stack** 완성 — 서버 측 rate limiter(cycle 0~5)와 클라이언트 측 대응(cycle 6)이 상보적으로 작동:

- **서버**: 정확한 한도 enforcement + 표준 헤더(`Limit/Remaining/Retry-After/Throttled/Throttle-Ms`) emit
- **클라이언트**: 헤더 인지로 자제(throttle 대기)·재시도(backoff)·캐싱(부하 자체 차단)

ch04가 "클라이언트 모범 사례" 한 절로만 다룬 이 contract를, **서버 측 cycle 0~5 산출물이 그대로 입력으로 들어가야** 의미를 가진다는 점이 직접 구현으로 드러남. 특히 cycle 5에서 만든 `X-Ratelimit-Throttled` 헤더 — 서버 입장에서는 단순 marker였는데, cycle 6 클라이언트 입장에서는 "다음 호출을 미루라"는 능동 신호. **헤더 하나가 양쪽에서 다른 역할을 함**.

남은 cycle 7: 회고 — 스킵한 알고리즘 정리 + ch04 후반 토픽 위치 정리 + 정직성 점검.

---

## Cycle 7 — 회고 (마지막 사이클)

**목표**: 코드 없는 사이클. 스킵한 알고리즘 2개와 다루지 않은 ch04 후반 토픽이 무엇이고 왜 안 했는지를 정직하게 정리. 그리고 cycle 5 즈음 사용자와의 대화에서 드러난 정직성 결함들을 cycle 0~6 전체 관점에서 회고.

cycle 7에 코드 변경 0줄, 테스트 변경 0줄. 글만.

### 7-1. 스킵한 알고리즘 2개 — 왜 안 했고, 실세계 어디서 쓰나

ch04 비교표의 5개 알고리즘 중 우리는 3개만 full 구현 (token bucket / fixed window / sliding window log). 두 개를 의도적으로 스킵:

#### [[leaking-bucket-algorithm]]

**왜 스킵**: token bucket의 "거울" 알고리즘이라 학습 가치가 추가되는 게 적다고 판단. token bucket이 "burst 흡수 + 평균 rate 제한"이라면, leaking bucket은 "burst 절대 없음 + 정확히 fixed rate 출력". 양쪽 다 cycle 1·3에서 충분히 다룬 개념.

**구현 차이의 본질**:
- token bucket: 토큰을 저축하고 차감 — 입력 burst → 즉시 통과 (capacity까지)
- leaking bucket: FIFO 큐 + worker가 fixed rate로 dequeue — 입력 burst → 큐잉되거나 거부, 출력은 항상 평탄

**실세계 사용처**:
- **[[redis]] 없는 nginx의 `limit_req` 모듈** — 큐 + leak rate으로 백엔드 보호. 자세한 이유는 사용자와의 대화에서 정리한 대로 — nginx의 1차 목적이 "백엔드 평탄화"라 입력 burst를 흡수해서 통과시키는 token bucket보다 부드럽게 깎아내는 leaking bucket이 정합. **`nodelay` 옵션으로 token bucket 흉내**도 가능
- **Shopify** (ch04 인용) — e-commerce 거래 처리·재고 갱신을 백엔드가 평탄하게 받아야 하므로
- **메시지 큐 워커 throttle** — Kafka consumer가 downstream에 평탄 출력 필요할 때

**우리 knot에 적용해보면**: shorten 엔드포인트에 사실 leaking bucket이 더 자연스러울 수도 있음 (DB write 평탄화 측면). 우리가 SWL 선택한 건 학습 동기였음 (7-3 정직성 점검 참조).

#### [[sliding-window-counter-algorithm]]

**왜 스킵**: SWL과 fixed window의 절충. 두 양 극단을 cycle 2·3에서 잡았으므로 사이의 근사 알고리즘은 글로 충분.

**핵심 메커니즘**: 직전 윈도우 카운터와 현재 윈도우 카운터를 **가중치로 보간**:

```
score = current_count + previous_count × overlap_ratio
```

여기서 `overlap_ratio` = 직전 윈도우가 "지금-N초" 구간과 얼마나 겹치는지의 비율.

예 (limit=10/minute, 12:00:30 시점):
- 12:00:00~12:00:59 윈도우의 누적: 6
- 11:59:00~11:59:59 윈도우의 누적: 8
- overlap = (60 - 30) / 60 = 0.5
- score = 6 + 8 × 0.5 = **10** → 한도 도달

**메모리·정확도 트레이드오프**:

| | sliding_window_log | sliding_window_counter |
|---|---|---|
| 자료구조 | ZSET (모든 timestamp 저장) | string 카운터 2개 (직전·현재) |
| 메모리 | O(limit × 사용자) | **O(2 × 사용자)** |
| 정확도 | 정확 | 근사 (보간 가정: 직전 윈도우 트래픽이 균등 분포) |
| 경계 burst | 없음 | 없음 (보간 효과) |

**Cloudflare 4억 요청 실측에서 0.003% 오차** (ch04 인용). 즉 메모리 1/L (L = 한도) 줄이면서 정확도는 거의 손해 없음.

**우리 knot에 적용해보면**: shorten 한도가 10/min이라 SWL 메모리도 사용자당 ~280바이트로 미미. 한도가 1000/min만 되어도 sliding_window_counter가 ~28KB → 280바이트로 줄임. **실서비스라면 큰 한도일 때 적극 검토**.

### 7-2. ch04 후반 토픽 — 왜 안 했고, 어디서 다뤄지나

ch04 §"분산 환경의 난제" + §"성능과 운영"에는 본 프로젝트가 스코프 외로 둔 토픽 3가지가 더 있음.

#### 멀티 DC eventual consistency

ch04: *"DC 간 데이터 동기화는 eventual consistency. 강한 일관성을 요구하면 지연이 폭증. 상세는 ch06 key-value store에서."*

**우리가 안 한 이유**: 본 프로젝트는 단일 Redis 인스턴스. DC 간 카운터 동기화·conflict resolution은 본질적으로 [[ch06-design-key-value-store]] 주제 — CAP·quorum·sloppy quorum·vector clock 같은 패턴이 필요. ch06 ingest 시 이미 [[quorum-consensus]], [[vector-clock]], [[sloppy-quorum-hinted-handoff]] 페이지에서 다뤘음.

**knot이 다중 DC로 진화한다면**:
- Redis CRDT (예: PN-Counter) 또는 Redis Enterprise CRDB
- 또는 eventual consistency 받아들이고 DC별 quota 할당 + 주기적 reconciliation
- 정확한 글로벌 한도가 필요하면 strong consistency 카운터 서비스 (Spanner 등) — 지연 대가

#### OSI L3 차단 (iptables 등)

ch04: *"본 장은 layer 7 (HTTP). layer 3에서는 iptables 등으로 IP 차단 가능 — 비용은 싸지만 식별 정밀도 ↓."*

**우리가 안 한 이유**: knot은 L7 (FastAPI middleware). L3 차단은 OS·네트워크 영역이라 학습 프로젝트 스코프를 크게 벗어남.

**언제 L3가 필요**: 단순 봇·DDoS 차단처럼 **L7까지 도달하기 전 자원 절약**이 중요할 때. AWS Shield, Cloudflare 같은 edge가 L3·L4에서 1차 차단 후 L7으로 전달.

**knot 운영하려면**: 클라우드 환경의 보안 그룹·WAF 룰로 자명한 abuse 패턴(같은 IP에서 초당 1000+ 요청) 차단. 우리 L7 rate limiter는 그 후의 정밀 정책 담당.

#### Edge 분산 배치 (Cloudflare 194 edge)

ch04: *"Edge 가까이 배치: 사용자 지연 단축. Cloudflare는 194개 edge 서버 분산 배치."*

**우리가 안 한 이유**: 단일 호스트 + Docker Redis라 분산 자체가 없음.

**knot redirect가 진화한다면**:
- redirect는 **읽기 트래픽** — 사용자 근처 edge에서 처리해야 지연 적음
- ch05 [[consistent-hashing]]으로 코드별 캐시 노드 결정
- ch06 KV store(Cassandra/Dynamo)에 다지역 복제된 단축 매핑 저장
- ch08 URL Shortener 챕터가 정확히 이 진화를 다룸

**knot shorten의 진화**:
- shorten은 **쓰기 트래픽** — 중앙 write service로 유지 (또는 leader 노드 1곳)
- 코드 생성은 ch07 unique ID generator (Snowflake 같은)
- 글로벌 한도 enforcement는 위 "멀티 DC" 패턴 적용

### 7-3. knot 전체 정직성 점검 — cycle 5 즈음 사용자와의 대화에서 드러난 것들

cycle 5 작업 중 사용자가 DESIGN.md를 검토하면서 짚어준 정직성 결함 3가지. 이 회고 섹션에 영구 기록 (DESIGN.md는 정정하지 않기로 결정).

#### 결함 1 — SWL을 shorten에 선택한 진짜 이유

**spec에 적힌 이유**: "shorten은 쓰기·악용 방지라 엄격해야 함. ch04 §'알고리즘 선택 기준'의 *엄밀하게 막아야 함 → sliding window log* 패턴 적용".

**진짜 이유**: cycle 3에서 [[sliding-window-log-algorithm]]의 ZSET+Lua atomicity를 시연할 슬롯이 필요했고, knot 엔드포인트가 2개뿐이라 shorten이 유일한 후보였음. **알고리즘이 endpoint를 골랐지, endpoint가 알고리즘을 고른 게 아님**.

**실서비스라면**: shorten은 외부 결제 없고, 단축 코드 생성 비용도 낮음. AWS/Stripe/GitHub처럼 **token_bucket(burst=10, rate=10/min)이 더 자연스러움** — 사용자가 클립보드 10개 붙여넣기 같은 자연 burst 흡수 가능.

**왜 SWL 유지했나 (cycle 5 결정)**: cycle 5의 hard/soft 시연이 SWL에서 더 가시적 (throttle 시간 visible) — 학습 데모 가치가 더 큼. 알고리즘 변경 비용도 있음.

#### 결함 2 — "엔드포인트별 차등 = 다른 알고리즘"의 과장

**spec에 적힌 결론**: *"같은 시스템 안에 정반대 트래픽 특성이 공존하므로 단일 정책이 아닌 엔드포인트별 차등 정책이 필요"*.

**맞는 부분**: 차등 정책이 필요 — 거의 모든 실서비스가 그렇게 함.

**과장된 부분**: 우리는 "차등"을 **다른 알고리즘 두 개**로 풀었지만, 실세계 거의 모든 서비스는 **같은 알고리즘 + 다른 파라미터**로 충분:

| 서비스 | 알고리즘 | 차등 방식 |
|---|---|---|
| GitHub API | 전부 token bucket | 엔드포인트별 한도 (REST 5000/h, GraphQL 5000 points/h, Search 30/min) |
| Stripe | 전부 token bucket | 작업별 한도 |
| AWS | 전부 token bucket | API별 bucket 크기·refill rate |
| Twitter | 전부 token bucket | endpoint별 한도 |

**우리는 두 알고리즘을 의도적으로 공존시킴** — 학습 목적상 여러 알고리즘 시연하려고. "엔드포인트 성격이 너무 달라서 같은 알고리즘으론 표현 못 함"이라서가 아님.

#### 결함 3 — "다차원 키"의 두 직교 차원 혼동

**spec에 적힌 도식**: "`endpoint × identity × user_tier` 다차원".

**문제**: 두 가지 다른 개념을 하나로 묶음.

| 무엇 | 들어가는 차원 | 역할 |
|---|---|---|
| **Rule 매칭** (어떤 정책 적용?) | `endpoint` + `user_tier` | rules.yaml에서 매치할 rule 찾기 (rules.lookup) |
| **Counter 격리** (누구의 카운터?) | `endpoint` + `identity` | Redis key로 사용자별 분리 |

`user_tier`는 **정책 차등용**, `identity`는 **카운터 격리용**. 완전히 다른 목적인데 "다차원 키"라는 깔끔한 단어로 묶고 싶어서 합쳐버림.

코드는 실제로 두 개념을 분리 처리:

```python
# Rule 매칭에는 user_tier가 들어감 (identity 안 들어감)
entries = [("endpoint", endpoint), ("user_tier", user_tier)]
rule = rules.lookup(entries)

# Counter key에는 identity가 들어감 (user_tier 안 들어감)
key = f"knot:{endpoint}:{identity}"
```

**정직한 도식**: 두 직교 차원 (정책 매칭 차원 + 카운터 격리 차원).

### 7-4. knot 전체 회고 — 학습 자산으로서 무엇이 남았나

**구현한 것**:
- 알고리즘 3개 (token bucket / fixed window / sliding window log) + plug-in 추상화
- 다차원 규칙 매칭 + 핫리로드 (Lyft envoy nested descriptors)
- hard/soft 정책 + MAX_THROTTLE_MS 안전장치
- 클라이언트 SDK 4 권고 (캐시·한도 인지·우아한 429·exponential backoff)
- 49 tests + 부하 그래프 3개 + 클라이언트 비교 실측

**ch04 본문에 없는 학습 자산 11개 함정**:
1. fakeredis Lua = lupa 필요
2. redis-py `Script` 객체 stale client binding
3. httpx ASGITransport의 `request.client.host` 공통
4. 포트 8000 충돌 (Lemonade)
5. pandas `dt.floor("S")` deprecated
6. `df.to_markdown()` ↔ tabulate
7. middleware의 `from X import f`(symbol) vs `import as` monkeypatch 차이
8. macOS BSD `date`는 `+%s%3N` 미지원
9. bash `$status`는 zsh readonly
10. sliding_window_log + MAX_THROTTLE_MS = 빠른 burst soft 폴백 (실용성 한계)
11. PYTHONPATH 함정 — `uv run python scripts/...` 시 cwd 미포함

ch04는 알고리즘 본질만 다루고 production 라이브러리·운영 환경 디테일은 안 다룸. 직접 구현해야만 발견 가능한 사실들 — **본 프로젝트의 핵심 학습 가치**.

**책에 충실한 부분**:
- 5 알고리즘 본질 (각 의사코드 직역)
- 응답 헤더 표준 (`X-Ratelimit-*`)
- Lyft envoy yaml 포맷
- Lua atomic 원칙
- Redis 중앙 저장소
- hard/soft 트레이드오프 개념
- 클라이언트 4 권고

**책에서 의도적으로 확장**:
- ZSET member에 random hex (책의 묵시 가정 보강)
- race condition 실측 (101/200 vs 0/50)
- boundary burst 그래프 비교 (책은 글만)
- Lyft nested descriptors 활용 (책은 단일 descriptor)
- watchdog 핫리로드 메커니즘
- soft mode 구체 구현 (asyncio.sleep + Throttled 헤더 + MAX_THROTTLE_MS)
- 클라이언트 SDK 4 권고 직접 구현 + naive 비교 실측
- `X-Ratelimit-Throttled` 헤더 (책에 없는 커스텀)

**의도적으로 안 한 부분**:
- leaking_bucket / sliding_window_counter 구현 (7-1 정리)
- 멀티 DC / OSI L3 / edge 배치 (7-2 정리)

### 7-5. 다음에 같은 프로젝트 한다면 (1년 후 자신에게)

**할 것**:
- 처음부터 정직한 동기 기록 — "학습 슬롯 필요해서" vs "객관 최선이라서"를 명확히 분리
- 사이클 0에 "정직성 점검" 의례 추가 — 모든 spec에 "이 결정의 진짜 이유" 칸 두기
- DESIGN.md를 진행 중간에 작성하지 말기 — 사이클 N에서 본 사실이 N+1에서 뒤집힐 수 있음. 회고에서 한 번에 작성

**다르게 할 것**:
- shorten 알고리즘 선택을 cycle 3보다 일찍 confirm — "이 엔드포인트에 SWL이 정말 어울리나" 의문 시점부터 의식했어야
- "차등 정책 = 다른 알고리즘" 도식을 cycle 1 즈음에 의심 — Stripe/GitHub 같은 실세계 예시 미리 조사
- cycle 2 demo lite처럼 알고리즘을 학습 가치만 보고 "구현 안 하되 회고로 정리"하는 결정을 cycle 1~3 사이에 더 일찍 — 우리는 cycle 1 회고 시점에야 9→7 단축

**유지할 것**:
- TDD red-green 사이클 — 학습 누적 효과가 극적이었음 (cycle 1~3까지 함정 다 잡힌 후 cycle 4~6은 거의 무경험으로 작동)
- 사이클별 sub-spec + plan + 회고의 3층 분리 — 너무 무겁지 않으면서 결정 이력 추적 가능
- wiki/projects/knot.md를 시간순 다이어리로 두기 — 옵시디언 그래프와 자연 결합
- subagent-driven implementation — 매 task 후 ch04 매핑 설명이 학습 강화. 컨텍스트 격리도 효과

### 7-6. 마무리

knot 프로젝트의 **공식 종료**.

**최종 산출**:
- 코드: `experiments/knot/` (~1500 LoC, 49 tests, 11 commits에 분산)
- 문서: spec 7개 + plan 7개 + DESIGN.md + 본 wiki 페이지
- 데이터: reports/*.md + PNG 3종 + client_comparison.md
- 학습: ch04 비교표 5셀 중 3 그래프 증명 + 11 실전 함정 + 정직성 점검 3건

ch04 학습의 한 closed loop 완성. 다음 챕터 학습이나 실제 시스템 적용 시 본 프로젝트의 결정·실측·함정 기록이 reference로 활용 가능.

knot 캐리어 자체는 ch08 URL Shortener 학습 시 다시 등장 — 그때는 redirect/shorten 두 서비스가 진짜 분리되고, ch05·06·07의 패턴(consistent hashing, KV store, unique ID generator)이 결합. rate limiter 미들웨어 코드는 거의 그대로 양쪽에 이식 가능.
