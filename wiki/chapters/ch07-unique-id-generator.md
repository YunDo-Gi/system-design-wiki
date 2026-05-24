---
chapter: 7
title_en: Design a Unique ID Generator in Distributed Systems
title_ko: 분산 시스템의 unique ID 생성기 설계
ingested_at: 2026-05-25
---

# Design a Unique ID Generator in Distributed Systems

## 핵심 takeaway

- 분산 환경에서 unique ID는 **요구사항 조합이 까다로워 단일 정답이 없음** — unique·64-bit·시간순·고처리량을 동시에 만족하려면 4가지 후보 알고리즘의 트레이드오프를 알아야 함.
- 책의 결론은 **Twitter snowflake** — 4 후보 (multi-master replication, UUID, ticket server, snowflake) 중 모든 요구사항을 만족하는 유일한 선택 (ch07, p.117).
- **"Divide and conquer" ID 설계**가 핵심 통찰 — 64-bit ID를 한 번에 만들지 말고 의미 있는 섹션(timestamp + DC + machine + 순번)으로 나눠 각 섹션을 다른 출처에서 생성. coordination 비용 0.
- Snowflake는 **시각 동기화 인프라([[network-time-protocol]])가 전제**. 머신 시계가 어긋나면 ID 충돌·역순 가능. 운영 가능한 구현은 시계 뒤점프 방어 분기 필수.
- 본 챕터는 **알고리즘 비교가 본질** — 시스템 아키텍처 설계라기보단 알고리즘 선택 문제. 4 후보의 단점을 정확히 알아야 snowflake 정당화 가능.

## 개요 — 왜 distributed unique ID가 어려운가

단일 DB의 `auto_increment`는 분산 환경에서 작동 안 함 (ch07, p.111):

- 단일 DB가 받을 수 있는 쓰기량 한계
- 다중 DB에서 같은 ID 발급 시 충돌
- 다중 DC에서 round-trip이 비싸 coordination 어려움

분산 unique ID의 일반적 요구사항 (ch07, p.113 인터뷰 시나리오):

| 요구사항 | 의미 |
|---|---|
| **Unique** | 충돌 0 |
| **Numerical** | DB index 효율, 정렬 |
| **64-bit fit** | 모바일·DB column 크기 표준 |
| **Ordered by date** | timeline·feed 자연 정렬 |
| **High throughput** | 예: 10K/s 이상 |

이 5가지를 동시에 만족시키는 게 본 챕터의 도전.

## 4가지 접근의 비교

| 접근 | unique | 64-bit | 시간순 | 분산 | 처리량 | 핵심 약점 |
|---|---|---|---|---|---|---|
| [[multi-master-id-replication]] | ✅ | ✅ | ❌ | 부분적 | 중 | DC 추가 어려움, 시간순 ✗ |
| [[uuid]] | ✅ | ❌ (128bit) | ❌ | ✅ | 높음 | 128-bit, 비숫자, 시간순 ✗ |
| [[ticket-server]] | ✅ | ✅ | ✅ | ❌ (SPOF) | 낮음 | SPOF + DB 락 병목 |
| **[[snowflake-id]]** | ✅ | ✅ | ✅ | ✅ | 높음 | 시각 동기화 의존 |

ch07의 결론 (p.117): "*We settle on snowflake as it supports all our use cases and is scalable in a distributed environment.*"

각 알고리즘의 동작·트레이드오프 상세는 위 위키링크 페이지들 참조.

## Snowflake 비트 분할

```
┌─┬───────────────────────────────────────┬─────────┬─────────┬─────────────┐
│0│         timestamp (41 bits)           │ dc (5)  │ mc (5)  │   seq (12)  │
└─┴───────────────────────────────────────┴─────────┴─────────┴─────────────┘
  └───────────────────── 64 bits ───────────────────────────────────────────┘
```

| 섹션 | 비트 | 의미 | 출처 |
|---|---:|---|---|
| sign | 1 | 항상 0 (signed integer 호환) | 고정 |
| **timestamp** | **41** | custom epoch 이후 ms | 시스템 시각 (`now() - epoch`) |
| datacenter ID | 5 | DC 식별자 (max 32) | 시작 시 config |
| machine ID | 5 | 같은 DC 안 머신 식별자 (max 32) | 시작 시 config |
| sequence | 12 | 같은 ms 안 순번 (max 4096) | 요청마다 increment, ms 바뀌면 0 |

기본값으로 **머신당 ms당 4096개 = 초당 ~409만 ID**, **~69년 운영 가능**. 책 요구사항(10K/s)을 훨씬 초과.

자세한 동작·튜닝은 [[snowflake-id]] 참조.

## 운영 추가 토픽 (ch07 §"Wrap up", p.117)

ch07이 면접 마지막에 짧게 던지는 3가지:

### Clock synchronization

snowflake는 서버 시계 일치 가정. multi-core·multi-machine 환경에서 시각 차이는 본질적 문제. **NTP**가 표준 해법 — [[network-time-protocol]] 참조. 시계 뒤점프 시 ID 충돌 방어 분기 필수.

### Section length tuning

기본 비트 분할(41+5+5+12)은 Twitter 기본값. 변경 가능:
- low concurrency·long term 운영 → sequence ↓, timestamp ↑ (더 오래 작동)
- high concurrency·short window → sequence ↑, timestamp ↓
- 글로벌 → datacenter ID ↑, machine ID ↓

단 **운영 중 비트 분할 변경은 위험** — 기존 ID와 충돌 가능. 처음에 신중히.

### High availability

ID generator는 **mission-critical** — 죽으면 신규 데이터 0. 머신 여러 대 분산 운영 (각자 다른 machine ID) + health check + failover.

## 등장 개념

- [[unique-id-generation-in-distributed-systems]] — 총론. 요구사항·4 후보 비교
- [[snowflake-id]] — 본 챕터의 결론 알고리즘. 64-bit 비트 분할
- [[uuid]] — 4 후보 중 하나. 128-bit coordination-free
- [[multi-master-id-replication]] — 4 후보 중 하나. `auto_increment` step 분할
- [[ticket-server]] — 4 후보 중 하나. Flickr 패턴, SPOF
- [[network-time-protocol]] — snowflake가 의존하는 시계 동기화 인프라 (ch04와 공유)

## 등장 기술

본 챕터엔 새 기술 컴포넌트 없음. snowflake는 Twitter 오픈소스 구현체이지만 본질이 알고리즘이라 concept으로 분류.

## 면접 관점 메모

- 4 후보 다 외워두고 각 약점 말할 수 있어야 (multi-master: DC 확장·시간순 / UUID: 128bit·시간순 / ticket: SPOF·DB락 / snowflake: 시계 의존)
- snowflake 비트 분할(1+41+5+5+12=64)과 함의(69년·4096/ms)를 즉시 말할 수 있으면 좋음
- 시계 동기화·section tuning·HA 같은 운영 토픽이 추가 점수 — ch04 §"분산 환경"과 같은 맥락
