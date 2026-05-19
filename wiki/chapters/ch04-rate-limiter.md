---
chapter: 4
title_en: Design a Rate Limiter
title_ko: 처리율 제한 장치 설계
ingested_at: 2026-05-19
---

# Design a Rate Limiter

## 핵심 takeaway

- Rate limiter는 **DoS 차단·비용 절감·서버 보호**를 위해 임계치 초과 트래픽을 거르는 컴포넌트. 위치는 client/server 양쪽 가능하지만 **server-side 또는 [[api-gateway]] 미들웨어**가 표준 (ch04, p.55-58).
- 5개 핵심 알고리즘 — [[token-bucket-algorithm]] (버스트 허용, AWS·Stripe), [[leaking-bucket-algorithm]] (FIFO, 일정 outflow, Shopify), [[fixed-window-counter-algorithm]] (단순하지만 경계 burst 취약), [[sliding-window-log-algorithm]] (정확, 메모리 비쌈), [[sliding-window-counter-algorithm]] (근사·메모리 효율, Cloudflare 검증 0.003% 오차) (ch04, p.59-65).
- 단일 노드 구현은 쉽지만 **분산 환경의 race condition·synchronization이 진짜 어려움**: 락 대신 **Lua 스크립트**·**Redis sorted set**, sticky session 대신 **중앙 데이터 스토어([[redis]])** (ch04, p.71-73).
- 클라이언트에 상태를 정확히 전달: 응답은 **HTTP 429**, 헤더는 `X-Ratelimit-Remaining` / `Limit` / `Retry-After` (ch04, p.69).

## 본문 요약

### Step 1 — 범위 (ch04, p.56)

요구사항 요약: 정확한 초과 차단 / 낮은 지연 / 메모리 효율 / 분산 공유 / 명확한 예외 전달 / 부분 장애 시 시스템 전체 무영향.

### Step 2 — high-level 설계: 위치와 알고리즘 (ch04, p.57-65)

**위치**: client는 위·변조에 취약 → server-side 미들웨어 또는 [[api-gateway]]가 표준. 직접 구현 vs 게이트웨이 선택은 기술 스택·인력에 따른 트레이드오프.

**알고리즘 비교** (각각 별도 페이지에 상세):

| 알고리즘 | 정확도 | 메모리 | 버스트 | 비고 |
|---|---|---|---|---|
| [[token-bucket-algorithm]] | 중 | 적음 | 허용 | AWS, Stripe |
| [[leaking-bucket-algorithm]] | 중 | 적음 | 평탄화 | Shopify |
| [[fixed-window-counter-algorithm]] | 낮음 | 적음 | 경계 burst 취약 | 단순 |
| [[sliding-window-log-algorithm]] | 높음 | **많음** | — | 모든 timestamp 저장 |
| [[sliding-window-counter-algorithm]] | 중·근사 | 적음 | 평탄화 | Cloudflare 오차 0.003% |

**기본 아키텍처** (Figure 4-12): 카운터는 DB가 아니라 **[[redis]]의 INCR/EXPIRE**로 관리.

### Step 3 — Deep dive (ch04, p.67-75)

**Rate limiting rules** (ch04, p.68): Lyft가 오픈소스한 yaml 포맷. domain/descriptors/key·value/unit·requests_per_unit. 디스크에 저장, worker가 캐시로 적재.

**제한 초과 응답** (ch04, p.69):

- HTTP **429 Too Many Requests**
- 헤더: `X-Ratelimit-Remaining`, `X-Ratelimit-Limit`, `X-Ratelimit-Retry-After`
- 사용 사례 따라 큐로 보내서 후처리(예: 일시 과부하 시 주문 보존)

**Detailed design** (Figure 4-13): 클라이언트 → rate limiter 미들웨어 → (Redis 카운터/캐시된 규칙 조회) → API 서버 또는 429 + (drop 또는 message queue).

**분산 환경의 두 난제** (ch04, p.71-72):

1. **Race condition**: `read → check → increment`이 비원자적. 락은 느리므로 **Redis Lua 스크립트** 또는 **sorted set**으로 원자화.
2. **Synchronization**: 여러 rate limiter 서버 간 상태 불일치. sticky session은 비추(확장·유연성 ↓) → **중앙 [[redis]] 같은 공유 스토어** 사용 ([[stateless-web-tier]] 원칙의 연장).

**성능 최적화** (ch04, p.73-74): edge 서버 활용으로 지연 단축 (Cloudflare 194개 edge 사례). DC 간 데이터는 **eventual consistency** 모델로 동기화 ([[multi-data-center]] 참조; consistency 상세는 ch06).

**모니터링**: 알고리즘과 규칙이 실제로 효과적인지 측정 — 너무 엄격하면 정상 요청 다수 drop, 너무 느슨하면 flash sale 같은 급증 못 막음 → 알고리즘 교체(예: 버스트가 필요하면 token bucket).

### Step 4 — Wrap up 추가 토픽 (ch04, p.75)

- **Hard vs soft**: hard = 임계 초과 절대 불가 / soft = 단기 초과 허용.
- **OSI 레이어**: 본 장은 layer 7(HTTP) 기준. layer 3에서는 `iptables`로 IP 기반 차단 가능.
- **클라이언트 모범 사례**: 응답 캐시·한도 인지·예외 처리·충분한 backoff.

## 등장 개념

- [[rate-limiting]] — 정의·필요성·위치·hard vs soft·OSI 레이어 총론
- [[token-bucket-algorithm]] — 토큰 버킷
- [[leaking-bucket-algorithm]] — 누출 버킷 (FIFO)
- [[fixed-window-counter-algorithm]] — 고정 윈도우 카운터
- [[sliding-window-log-algorithm]] — 슬라이딩 윈도우 로그
- [[sliding-window-counter-algorithm]] — 슬라이딩 윈도우 카운터 (하이브리드)
- 분산 이슈는 본 페이지 Step 3 본문에 정리 (race condition, synchronization)
- 관련: [[caching-strategies]], [[stateless-web-tier]], [[multi-data-center]]

## 등장 기술

- [[redis]] — INCR/EXPIRE로 카운터 관리, Lua·sorted set으로 원자성
- [[api-gateway]] — rate limit/SSL termination/auth/IP whitelisting 미들웨어

## 면접 관점 메모

- **알고리즘 선택 근거**를 트레이드오프로 답해야 함. "정확하게 막아야 한다" → sliding window log; "버스트 허용 + 메모리 효율" → token bucket; "outflow 평탄화" → leaking bucket; "근사 OK + 메모리 효율" → sliding window counter.
- 분산 race condition 질문 — 락이 정답이 아니라 **원자 연산(Lua/sorted set)** 이 정답.
- 클라이언트 UX(429 + 헤더 + retry-after)와 운영 모니터링은 자주 빠지는 가점 포인트.
- 후속 연결: race condition·sorted set은 [[consistent-hashing]] (ch05)·key-value store 일관성 (ch06)으로 이어진다.
