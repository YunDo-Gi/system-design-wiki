---
type: concept
tags: [distributed-systems, unique-id]
sources: [ch07]
---

# UUID (Universally Unique Identifier)

## 한 줄 정의

**128-bit 식별자**. 서버 간 조정 없이 각 노드가 독립적으로 충돌 없이 생성 가능. ch07이 분산 unique ID의 4가지 후보 중 하나로 평가 — coordination-free의 대표 (ch07, p.113).

예: `09c93e62-50b4-468d-bf8a-c07e1040bfb2` (UUID v4, 32 hex digits + 4 dashes)

## 왜 필요한가

분산 환경에서 서로 다른 서버가 **사전 조정 없이** unique ID를 만들어야 할 때. 충돌 확률이 사실상 0이므로 (아래) 머신끼리 통신·중앙 권한·시각 동기화 없이 동작.

ch07이 인용한 Wikipedia: *"after generating 1 billion UUIDs every second for approximately 100 years would the probability of creating a single duplicate reach 50%"* — 즉 사실상 충돌 불가능.

## 핵심 메커니즘

### 비트 구조 (UUID v4 — 가장 흔한 형태)

```
xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
        128 bits = 32 hex chars + 4 dashes

- 122 random bits + 6 deterministic bits (version=4, variant=10)
- random source: cryptographically secure random
```

다른 버전(v1: timestamp + MAC, v3/v5: namespace + name 해시, v6/v7/v8: 시간순 정렬 가능)도 있지만 분산 시스템에서 가장 많이 쓰이는 건 v4.

### 충돌 확률

- 128-bit = 2^128 ≈ 3.4 × 10^38 가능한 값
- Birthday paradox 적용: 50% 충돌 도달까지 ~2^64 = 1.8 × 10^19 생성 필요
- 초당 10억 개 100년 = 3.15 × 10^18 — 50% 도달 못 함
- 실용적으로 **충돌은 무시 가능**

## 트레이드오프 & 선택 기준

### Pros

- **Coordination-free** — 서버끼리 통신 없음. 시각 동기화·중앙 권한 불필요
- **충돌 확률 사실상 0**
- **모든 언어·플랫폼 표준 지원** — Python `uuid.uuid4()`, Java `UUID.randomUUID()`, JS `crypto.randomUUID()`
- **시작 시 머신 설정 불필요** — [[snowflake-id]]의 DC/machine ID 같은 부담 없음

### Cons

- **128-bit** — ch07 요구사항(64-bit fit)을 안 맞음. DB 인덱스 크기 2배. 모바일 클라이언트 호환 문제
- **시간순 정렬 불가** (v4 기준) — 시간 정보 없음. timeline·feed에 부적합
- **숫자가 아님** — hex 문자열. DB index 효율 ↓, 정렬 ↓
- **저장 공간** — 36자 문자열 또는 16 바이트 binary
- **랜덤이라 DB 인덱스의 캐시 효율 ↓** — 연속된 ID가 디스크상 인접하지 않음 (B-tree page split 자주)

### 언제 쓰고 언제 안 쓰는가

**쓰는 게 자연스러운 경우**:
- 머신 간 시각 동기화 보장 안 됨 → [[snowflake-id]] 부적합
- 단순함·인프라 0이 최우선
- 짧은 시간 안에 많은 임시 ID (correlation ID·request ID 같은 trace 목적)
- 클라이언트가 미리 ID를 만들어 보내야 하는 경우 (write-then-confirm 패턴)

**다른 답이 나을 수 있는 경우**:
- 64-bit 필수 → [[snowflake-id]] 또는 [[ticket-server]]
- 시간순 정렬 필요 → snowflake, ticket server, UUID v6/v7
- DB primary key 빈번 lookup → 짧고 시간순인 게 더 효율

## 다른 개념과의 관계

- [[unique-id-generation-in-distributed-systems]] — 본 페이지를 포함한 4가지 접근의 비교 총론
- [[snowflake-id]] — UUID의 약점(128bit·시간순 X)을 보완한 대안. 둘이 거의 양극단
- [[ticket-server]] — 중앙 협조 패턴 (UUID 정반대)
- 모든 분산 시스템의 trace·correlation ID — distributed tracing에서 UUID 흔히 사용 (시각 정렬은 별도 timestamp field로)

## 등장 사례

- ch07 — 분산 unique ID 4 후보 중 하나로 평가, snowflake에 밀려 채택 X
- 거의 모든 언어 표준 라이브러리 — Python `uuid`, Go `crypto/rand` + UUID 패키지, JS Web Crypto
- AWS (S3 object ID 등), Kubernetes (pod ID·UID), Docker (container ID short hash가 UUID 일부)
- Distributed tracing — Jaeger/Zipkin의 trace ID·span ID
- 데이터베이스 — PostgreSQL `uuid` 컬럼 타입, MongoDB `_id`(기본은 ObjectID지만 UUID 옵션)

## 면접 관점 메모

ch07 4 옵션 중 "coordination-free"의 대표. snowflake 채택 정당화하려면 UUID의 약점(128bit·시간순 X)을 정확히 알아야. **랜덤한 1B/s × 100년 = 50% 충돌**이라는 수치가 인상적이라 인용 가치 있음.
