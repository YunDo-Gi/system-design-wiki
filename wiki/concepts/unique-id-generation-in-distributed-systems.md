---
type: concept
tags: [distributed-systems, unique-id]
sources: [ch07]
---

# Unique ID Generation in Distributed Systems

## 한 줄 정의

여러 서버·DC에 걸쳐 **충돌 없이 unique한 ID를 만드는 문제**. 단일 DB의 `auto_increment`는 분산 환경에서 깨지므로 별도 패턴 필요.

## 왜 필요한가

ch07 (p.111): "*Your first thought might be to use a primary key with the auto_increment attribute in a traditional database. However, auto_increment does not work in a distributed environment because a single database server is not large enough and generating unique IDs across multiple databases with minimal delay is challenging.*"

전형적 요구사항 (ch07 인터뷰 시나리오 기준):
- **Unique** — 충돌 없음
- **Numerical values** (선택) — DB index 효율, 64-bit 호환
- **64-bit fit** (선택) — 모바일·DB 컬럼 크기
- **Ordered by date** — 시간순 정렬 가능 (timeline·feed 표시 자연)
- **처리량** — 예: 10K/s 이상 생성

요구사항 조합이 까다로워서 **모든 걸 동시에 만족시키는 단일 답이 없음** → 4가지 접근의 트레이드오프.

## 핵심 메커니즘 (4가지 접근 비교)

### 1. Multi-master replication

[[multi-master-id-replication]] — DB의 `auto_increment` step을 서버 수 N으로 두기. 서버 1은 1,3,5,...; 서버 2는 2,4,6,...

- ✅ 단순. 익숙한 SQL
- ❌ **DC·서버 추가/제거 어려움** (전체 step 재계산 필요). 시간순 ✗

### 2. UUID

[[uuid]] — 128-bit 랜덤 식별자. 서버 간 조정 없이 독립 생성.

- ✅ Coordination-free. 충돌 확률 사실상 0
- ❌ **128-bit** (요구 64-bit 초과). 시간순 ✗. 비숫자

### 3. Ticket server

[[ticket-server]] — 중앙 ticket server에 `auto_increment` 위임. Flickr 패턴.

- ✅ 숫자 ID. 시간순. 구현 단순
- ❌ **SPOF**. 다중 ticket server 두면 동기화 문제

### 4. Twitter snowflake

[[snowflake-id]] — 64-bit를 시간 + DC + 머신 + 순번으로 분할.

- ✅ **모두 만족** (unique, 64-bit, 시간순, 분산, 고처리량)
- ❌ 시각 동기화 의존 ([[network-time-protocol]] 필요)

## 트레이드오프 & 선택 기준

| 요구사항 우선순위 | 권장 |
|---|---|
| 단순함·내부 단일 DB | auto_increment 그대로 |
| 단순함·소규모 분산 | [[ticket-server]] (SPOF 감수) |
| 시각 동기화 환경 X | [[uuid]] (시계 무관) |
| 모든 요구사항 (분산+64-bit+시간순+처리량) | **[[snowflake-id]]** ← 책의 결론 |
| 보안상 ID 예측 불가능해야 | random + collision check (snowflake는 예측 가능) |

ch07의 결론 (p.117): "*We settle on snowflake as it supports all our use cases and is scalable in a distributed environment.*"

## 실무 적용 시 고려사항

1. **요구사항 명확화 먼저** — 인터뷰에서 "ID가 어떤 특성을 가져야 하나? 64-bit? 시간순? 숫자?" 질문이 critical. 답에 따라 권장 알고리즘 달라짐 (p.113 candidate-interviewer 대화)
2. **보안 측면**: snowflake는 timestamp/머신을 노출 — 비밀번호 reset token처럼 예측 불가능해야 하는 경우엔 부적합
3. **시각 동기화 인프라** — snowflake 채택 시 NTP 환경이 전제. AWS는 NTP 제공, 자체 DC면 구축 필요
4. **High availability** — ID generator가 죽으면 신규 데이터 생성 중단. mission-critical 운영 (p.117 wrap-up)
5. **section length tuning** — snowflake 비트 분할 변경은 신중. 한 번 발급 시작하면 변경이 기존 ID와 충돌 가능
6. **URL 단축처럼 짧은 키 공간** — snowflake는 64-bit라 길음. base62 encoding으로 짧게 만들거나 (knot처럼) random + collision check가 더 짧게

## 다른 개념과의 관계

- [[snowflake-id]], [[uuid]], [[multi-master-id-replication]], [[ticket-server]] — 본 페이지가 비교한 4가지 접근의 각 상세 페이지
- [[network-time-protocol]] — snowflake가 의존하는 시계 동기화 인프라
- [[consistent-hashing]] (ch05) — sharding key 결정에 ID 패턴 영향 (예: snowflake의 timestamp prefix가 hotspot 만들 수 있음)
- [[sloppy-quorum-hinted-handoff]] (ch06) — ID generator가 다중 노드일 때 가용성 보장 패턴 응용 가능

## 등장 사례

- ch07 — 본 챕터의 주제. 4가지 접근 비교 후 snowflake 채택
- DB primary key, 메시지 ID, 트랜잭션 ID, URL shortcode — 거의 모든 분산 시스템의 ID 발급 문제
- Twitter — snowflake 원형 (tweet ID)
- Flickr — ticket server (photo ID)
- AWS, GCP 같은 cloud — 내부적으로 UUID 또는 snowflake 변형
- knot (ch04 학습 프로젝트) — 현재 `secrets.token_urlsafe(6)` (random 6 chars). ch08 URL Shortener 진화 시 [[snowflake-id]] 또는 base62 conversion으로 교체 예정

## 면접 관점 메모

ch07 자체가 ID generator 면접 질문이라, **요구사항 명확화 → 4 옵션 나열 + 각 트레이드오프 → snowflake 채택 + 비트 분할 설명**이 표준 흐름. 4 옵션 다 알아야 비교 가능.
