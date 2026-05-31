# knot — URL 단축 SaaS 설계

> 책 *"가상 면접 사례로 배우는 대규모 시스템 설계 기초"* (Alex Xu, 2nd ed.)의 각 챕터에서 적용한 개념과 설계 선택 이유를 챕터별로 정리. **현재 운영 가능한 상태 기준** (과거 변경·제거 이력 기록 안 함 — `git log` 참조).
>
> 새 챕터를 학습하면서 적용된 패턴이 늘어나면 해당 섹션이 추가/갱신된다.

## 0. 서비스 개요

knot은 URL 단축 SaaS의 mock 구현. 두 엔드포인트:

| 엔드포인트 | 동작 | 부하 특성 |
|---|---|---|
| `POST /shorten` | URL 입력 → 단축 코드(`abc123`) 발급 | 쓰기, 빡빡 한도 |
| `GET /{code}` | 단축 코드로 원본 URL 302 redirect | 읽기, 트래픽 폭증 위험 |

- **인증**: `X-API-Key` 헤더 (shorten), 익명 IP (redirect)
- **티어**: `X-User-Tier` 헤더 (`free` 기본 / `premium` / `enterprise`)
- **저장소**: 단축 코드는 in-memory dict (실서비스는 ch06 KV store로 진화 예정)
- **인프라**: FastAPI + Redis (docker-compose)

---

## ch04 — Rate Limiter

### 적용된 개념

- **알고리즘**: [[token-bucket-algorithm]] (양쪽 엔드포인트)
- **자료구조**: Redis HASH (`tokens`, `last_refill` 두 필드)
- **Atomicity**: Lua script + `redis.call('TIME')` (clock skew 면역)
- **정책 매칭**: Lyft envoy 중첩 descriptors — `endpoint × user_tier` 다차원, specificity 우선
- **운영 유연성**: watchdog 파일 watcher 핫리로드 (atomic swap)
- **응답 표준**: `X-Ratelimit-Limit/Remaining/Retry-After` + 429 (책 표준 그대로)
- **클라이언트 모범 사례**: KnotClient SDK — 5분 TTL 캐시 + exponential backoff (`Retry-After` 존중)

### 현재 정책

```yaml
shorten free:       token_bucket, 10/min, burst 10
shorten premium:    token_bucket, 50/min, burst 50
shorten enterprise: token_bucket, 500/min, burst 500
redirect (모두):    token_bucket, 50/s, burst 100
```

### 설계 선택 이유

**① 왜 token_bucket을 양쪽 모두에?**

| 알고리즘 | knot에서 평가 | 이유 |
|---|---|---|
| **token bucket** ✅ | 채택 | 사용자 burst가 자연 (탭 여러 개 열기, 클립보드 다중 단축). capacity가 burst 흡수, rate가 평균 한도. **AWS/Stripe/Twitter/GitHub 모두 token bucket** |
| sliding window log | ✗ | 정확하지만 메모리 비쌈. knot 한도(10~500/min)엔 과함. shorten에 적용 가능했지만 실서비스 표준 아님 |
| fixed window | ✗ | 윈도 경계 burst (분당 100 → 2초간 200 통과 가능). 쓰기엔 위험 |
| leaking bucket | ✗ | FIFO 큐 + worker, 처리율 고정. nginx/Shopify가 백엔드 평탄화 목적으로 씀. HTTP API에선 사용자 burst를 거부/큐잉 — UX 나쁨 |
| sliding window counter | ✗ | sliding log의 근사. 메모리 적지만 token bucket의 burst 흡수가 더 직관 |

**② 왜 in-process middleware? (FastAPI BaseHTTPMiddleware)**

| 옵션 | 평가 |
|---|---|
| API gateway (Envoy/Nginx/Kong) | 운영 표준이지만 **별도 운영 컴포넌트** 추가. knot 규모엔 과함 |
| **FastAPI middleware** ✅ | 인증 후 단계라 API key/tier 정보 활용. 별도 서비스 없이 한 프로세스 |
| Caddy/Nginx 레이어 (JWT 미파싱) | 사용자/팀 ID 모름 → IP 단위만 가능, 부적합 |

→ 서비스 규모 커지면 Envoy로 옮길 수 있게 알고리즘은 추상화 유지 (`Limiter` Protocol).

**③ 왜 Redis 단일 인스턴스? (책 권고 그대로)**

- *"카운터는 DB가 아니라 Redis에 둔다. INCR/EXPIRE로 자연스러운 카운터·TTL"*
- 다중 노드 확장 시 카운터 동기화 — 노드마다 자체 카운터면 정책 N배 폭증 (sticky session 안티패턴)
- Lua atomic으로 race condition 해결 — 락 사용 0회

**④ 왜 Lua atomic (vs WATCH/MULTI 옵티미스틱 락)?**

- 책: *"락은 답이 아니다 — 느리다. 표준 해법 ① Lua ② sorted set"*
- WATCH/MULTI는 충돌 시 재시도. Lua는 한 번에 atomic 완료
- 우리 token_bucket Lua: TIME + HMGET + 계산 + HMSET + EXPIRE를 한 덩어리로

**⑤ 왜 endpoint별 다른 파라미터, 같은 알고리즘?**

| 서비스 | 알고리즘 | 차등 방식 |
|---|---|---|
| GitHub API | 전부 token bucket | 한도만 다름 (REST 5000/h, GraphQL 5000pt/h, Search 30/min) |
| Stripe | 전부 token bucket | 작업별 한도 |
| AWS | 전부 token bucket | API별 bucket 크기·rate |
| **knot** | **전부 token bucket** | 엔드포인트별 한도·burst |

실세계 표준 — 차등은 **같은 알고리즘 + 다른 파라미터**로 충분. 알고리즘이 여러 개면 코드·운영 복잡도만 늘어남.

**⑥ 왜 user_tier 차등을 burst capacity로 표현?**

| 의도 | 실현 |
|---|---|
| premium은 더 많이 쓸 수 있음 | tier별 다른 `requests_per_unit` (free 10 / premium 50 / enterprise 500) |
| premium은 burst 흡수 받음 | tier별 다른 `burst` (free 10 / premium 50 / enterprise 500) |
| premium은 한도 hit 시 명확 안내 | 표준 `Retry-After` 헤더 — SDK가 자동 backoff |

**핵심 결정**: 한도 hit 시 **server-side throttle (asyncio.sleep) 안 함**. HTTP에서 server thread를 N초 잡으면 자원 낭비 + 동시 1000명 throttle = capacity 갉아먹는 DoS. 실세계는 전부 429 + `Retry-After` 힌트, 클라이언트가 자기 시간 자기가 sleep.

**⑦ 왜 핫리로드?**

- 정책 변경 시 앱 재시작 X → 운영 유연성
- watchdog 파일 watcher → yaml 수정 즉시 반영 (~100ms)
- atomic swap (새 Rules 객체 통째 교체) — partial reload 함정 회피, 실패 시 이전 정책 유지

**⑧ 장애 대응 (fail-open vs fail-close)**

| 엔드포인트 | Redis 장애 시 | 이유 |
|---|---|---|
| `GET /{code}` | **fail-open** (통과) | 읽기 + 트래픽 폭증 위험. 차단되면 정상 사용자 클릭 실패 — UX 직격 |
| `POST /shorten` | **fail-open** | knot은 외부 결제 없음. 단축 코드 발급은 무료, abuse 위험만 잠시 노출 |

`FAIL_MODE=open|closed` env로 토글 가능. 실서비스에서 외부 유료 API를 호출한다면 shorten은 fail-close 검토.

### 실세계 비교

| 서비스 | 알고리즘 | 정확도 | 주 목적 |
|---|---|---|---|
| GitHub/Stripe/AWS | token bucket | 중 | API 사용자 공평성 + burst 자연 흡수 |
| nginx `limit_req` | leaking bucket | 중 | 백엔드 평탄화 (큐 + fixed rate) |
| Cloudflare | sliding window counter | 높음 (근사, 0.003% 오차) | edge 정확 한도 + 메모리 적음 |
| knot | **token bucket** | 중 | API 표준 따름 |

### 알려진 한계

- knot은 한 머신 + Redis 단일 인스턴스 — 다중 캐시 노드 확장 시의 분배 전략 검토는 ch05 섹션 참조 (현 스케일 불필요, 실제 답은 CDN/매니지드 Redis로 결론)
- 단축 코드 저장은 in-memory dict — 프로세스 재시작 시 휘발. ch06 KV store로 교체 예정
- 코드 생성은 `secrets.token_urlsafe(6)` — 충돌 가능. ch07 unique ID generator로 교체 예정
- redirect는 중앙 단일 서비스 — 실서비스는 edge CDN 분산. ch08 URL Shortener에서 다룸

---

## ch05 — Consistent Hashing (미적용 — 의도된 결정)

> 결론: **knot 코드에 consistent hashing을 넣지 않는다.** 현 스케일에서 불필요하고, redirect 읽기 스케일의 실제 해법은 ch08의 CDN 엣지 캐싱이며, 앱 티어 캐시가 필요해지더라도 손수 짠 consistent hashing은 1순위가 아니기 때문. 개념 학습은 위키 [[consistent-hashing]]에 정리하고, knot은 §3-6("실제 필요한 것만 적용, 학습 동기 코드 금지")에 따라 비적용을 택한다.

### 왜 지금 불필요한가

- 단축 코드의 hot URL 워킹셋은 작고, **Redis 한 대로 초당 수만~수십만 조회**가 거뜬하다. redirect 읽기를 한 노드가 충분히 감당.
- consistent hashing은 "캐시를 여러 노드로 샤딩"한 **위에서야** 의미가 있는데, 다중 캐시 노드 자체가 현 규모엔 과잉이다. 받침이 없는 곳에 알고리즘만 얹는 꼴.

### 적용을 검토한 위치와 기각 이유

| 후보 위치 | 평가 | 기각 이유 |
|---|---|---|
| **redirect 읽기 캐시 샤딩** | 가장 그럴듯 | 다중 노드 자체가 현 불필요. 스케일이 와도 실제 답은 CDN(아래)·매니지드 Redis |
| rate-limit 카운터 샤딩 | ✗ | 다중 Redis 샤딩은 **Redis Cluster가 hash slot으로 대신** 해줌 → 앱 레이어에 직접 consistent hashing을 짜는 건 실무 비표준 |
| code→URL 저장소 샤딩 | ✗ (시기상조) | 이건 [[consistent-hashing]]이 아니라 ch06 KV store 영역. 그때 다룸 |

### 실제 스케일이 오면 무엇을 쓰나 (실세계)

| 상황 | 실세계 선택 | 비고 |
|---|---|---|
| redirect 읽기 폭증 | **CDN / 엣지 캐싱** | `code→URL`을 엣지에 캐싱, origin 우회 + 지리적 근접. Cloudflare Workers KV·Fastly. **ch08 주제** |
| 앱 티어 캐시 필요 | **매니지드 Redis / Redis Cluster** | 운영 시스템 1개·failover·복제 내장. hash slot으로 샤딩 위임 |
| 자기 memcached 함대 운영 + 비용 효율 절실 | memcached + 클라이언트 consistent hashing(ketama) | 거대 스케일·비용 최적화 특수 케이스. knot의 상황 아님 |

→ 즉 "consistent hashing을 직접 구현"은 맨 아래 특수 케이스에서나 순수 우위. knot은 그 상황이 아니다.

### 개념 비교 — memcached 클라이언트 샤딩 vs Redis Cluster

ch05를 학습할 때 가장 헷갈리는 지점이라 정리. **둘은 "샤딩을 누가 하느냐"가 정반대다.**

| | memcached 다중 노드 | Redis Cluster |
|---|---|---|
| 샤딩 주체 | **클라이언트** | 서버(클러스터) |
| 분배 방식 | **consistent hashing (ring)** | **hash slot (16384 고정 슬롯, `CRC16(key) % 16384`)** |
| failover/복제 | 없음 | 내장 |
| 자료구조/영속성 | 없음(순수 캐시) | 있음(데이터스토어) |

Redis Cluster는 애초에 consistent hashing을 **쓰지 않는다**(hash slot은 별개 메커니즘). 그래서 "Redis로 샤딩"을 고르면 ch05의 consistent hashing은 등장하지도 않는다.

### hotspot — 완화하는 경우 vs 못 하는 경우

consistent hashing의 hotspot 효과는 **키 개수**에 따라 갈린다 (혼동 주의).

| 문제 | CH 효과 |
|---|---|
| 서로 **다른 hot key 여러 개**가 한 shard에 충돌 (Katy Perry·Justin Bieber·Lady Gaga가 같은 shard) | **완화** ✅ — 균등 해시 + virtual nodes로 서로 다른 노드에 흩뿌림 |
| **단일 hot key 하나**가 자기 shard를 초과 (한 바이럴 링크에 클릭 폭주) | 못 함 ❌ — 키 하나는 못 쪼갬 → 복제·로컬 캐시·CDN으로 별도 해결 |

knot의 "인기 링크 여러 개가 캐시 노드에 몰림"은 전자(완화 가능), "바이럴 링크 하나에 폭주"는 후자(CH로는 부족)다.

### 등장 예정

- **ch08 (URL Shortener)** — redirect 읽기의 CDN/엣지 분산을 본격적으로 다룰 때, 본 결정(앱 티어 직접 샤딩 대신 엣지 캐싱)이 구체화된다.

---

## ch06 — Key-Value Store (예정)

knot의 단축 코드 매핑 저장소가 in-memory dict → 분산 KV로 진화할 때:

- redirect 읽기는 eventual consistency OK (단축 매핑은 한 번 발급 후 변경 안 됨)
- shorten 쓰기는 strong consistency 필요 (코드 충돌 방지)
- Cassandra/Dynamo 모델, quorum 패턴

(현재 in-memory mock)

---

## ch07 — Unique ID Generator (예정)

`secrets.token_urlsafe(6)` 충돌 가능성:

- 6 chars × base64 = 64⁶ ≈ 6.9×10¹⁰ — 일정 규모 넘으면 birthday paradox로 충돌
- 분산 환경에서 코드 발급 시 race condition

→ Snowflake 같은 분산 ID generator로 교체 예정.

---

## ch08 — URL Shortener (예정)

ch08은 책이 URL 단축 서비스를 본격 다루는 챕터. 그때 redirect/shorten 두 서비스의 진짜 분리:

| | shorten (write) | redirect (read) |
|---|---|---|
| QPS | 낮음 | 압도적으로 높음 |
| 저장소 | primary DB | read replica / KV / edge cache |
| 배포 | 중앙 1~몇 군데 | edge 가까이 다지역 |
| rate limit | API 키 단위 쿼터 | IP·지역 단위 abuse 방어 |

ch08 학습 시 본 DESIGN.md의 §0 서비스 개요 부분이 두 서비스로 분리되며 본격적 진화.

---

## 부록 — 코드 구조 (현재)

```
experiments/knot/
  app/
    main.py                      # FastAPI 앱, 라우트, lifespan (rules 로드 + watchdog 시작)
    middleware.py                # RateLimitMiddleware (식별·매칭·limiter 호출·헤더 주입·429)
    rules.py                     # Rules tree (DFS specificity matching) + start_watcher
    redis_client.py              # async Redis 싱글톤 (REDIS_URL env)
    limiter/
      base.py                    # Rule, Decision, Limiter Protocol
      registry.py                # algorithm 이름 → Limiter 인스턴스
      token_bucket.py            # 유일 알고리즘 — Lua script 로드 + register_script
      scripts/token_bucket.lua   # atomic: TIME + HMGET + 리필 + 차감 + HMSET + EXPIRE
  client/
    base.py                      # ShortenResult, RateLimitedResult dataclass
    naive.py                     # NaiveClient (httpx wrapper, baseline)
    sdk.py                       # KnotClient (cache + exponential backoff)
  rules.yaml                     # 정책 정의 (위 §ch04 §4 현재 정책 참조)
  scripts/
    compare_clients.py           # Naive vs SDK 비교 부하 시험
    report.py                    # k6 NDJSON → matplotlib → md (재사용)
  tests/
    unit/                        # fakeredis + freezegun, 알고리즘 본질·rules·SDK
    integration/                 # 실 Redis + httpx LifespanContext, e2e + race demo
  load/
    token_bucket.k6.js           # k6 시나리오 (burst·ramp·cycle)
  reports/
    token_bucket.md (+ PNG)      # k6 부하 결과
    client_comparison.md         # SDK vs Naive
  docker-compose.yml             # Redis 7-alpine
  pyproject.toml                 # uv project
  README.md                      # 빠른 시작
```

ch05~08 적용 시 이 구조에 추가될 디렉터리·모듈은 각 챕터 섹션에 기록.
