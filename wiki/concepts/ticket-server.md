---
type: concept
tags: [distributed-systems, unique-id, database]
sources: [ch07]
---

# Ticket Server

## 한 줄 정의

**중앙에 단일 ticket server (DB)를 두고 `auto_increment`로 unique ID를 발급**하는 패턴. Flickr가 2010년에 이 방식으로 분산 primary key 문제를 풀었음 (ch07, p.113). 단순함의 매력 vs SPOF 트레이드오프.

## 왜 필요한가

[[multi-master-id-replication]]보다 더 단순한 분산 ID 방법. 모든 분산 application 서버가 같은 ticket server를 두고 ID를 받음 → 발급 책임 한 곳에 집중하면서 application은 stateless 유지.

ch07 p.113: "*The idea is to use a centralized auto_increment feature in a single database server.*"

## 핵심 메커니즘

### 구조 (ch07, p.113 Figure 7-4)

```
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│Web Server│  │Web Server│  │Web Server│  │Web Server│
└────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘
     │             │             │             │
     └─────────────┴─────────────┴─────────────┘
                          │
                          ▼
                  ┌───────────────┐
                  │ Ticket Server │  ← 단일 DB, auto_increment 호스팅
                  └───────────────┘
```

application 서버가 새 ID 필요할 때마다 ticket server에 요청 → ticket server가 `auto_increment` 다음 값 반환.

### Flickr의 구현 트릭

실제 Flickr은 SPOF 우려로 ticket server를 **2개로 이중화** + 각자 다른 offset/step:
- ticket A: 1, 3, 5, ... (odd)
- ticket B: 2, 4, 6, ... (even)

→ 한쪽 죽어도 다른 쪽 계속 발급. 단 step 2이라 ID 공간 절반 손실. ([[multi-master-id-replication]]의 mini 버전과 같은 트릭)

## 트레이드오프

### Pros (ch07 p.113)

- **Numeric IDs** — auto_increment의 자연 결과
- **시간순 정렬** — 항상 증가
- **소·중규모에 쉬움** — 별도 라이브러리·알고리즘 없이 DB 한 대로

### Cons (ch07 p.114)

- **Single Point of Failure** — ticket server 죽으면 모든 application에서 ID 발급 중단 = 신규 데이터 생성 stop
- 다중 ticket server 두면 → multi-master와 같은 동기화 문제 발생 (offset/step 분할)
- **처리량 병목** — 단일 DB의 auto_increment 락 → 머신당 처리량 한계
- **네트워크 hop** — 매 ID 발급마다 ticket server에 round trip = 응답 지연 + 네트워크 부하

## 다른 알고리즘과의 위치

| | multi-master | UUID | **ticket** | snowflake |
|---|---|---|---|---|
| 분산 | 부분적 | ✅ | **❌ (SPOF)** | ✅ |
| 시간순 | ❌ | ❌ | **✅** | ✅ |
| 64-bit | ✅ | ❌ | **✅** | ✅ |
| 처리량 | 중 | 높음 | **낮음** | 높음 |
| 구현 단순성 | 중 | 매우 단순 | **매우 단순** | 중 |

→ ch07이 ticket server를 채택 안 한 이유: **SPOF + 단일 DB 처리량 한계**. snowflake에 밀림.

## 실무 적용 시 고려사항

1. **2개 이중화로 SPOF 일부 회피** — 단 step 2면 ID 공간 효율 50%. N개로 늘리면 효율 1/N
2. **batch fetch로 처리량 회복** — application이 매번 1개 받지 말고 `[100, 199]` 같은 100개 range 미리 받아두기. ticket server 부하 1/100. 단 application 죽으면 미사용 range 손실
3. **소·중규모에 최적** — Flickr이 채택한 시점은 사진 1억 개 정도. 글로벌 거대 서비스엔 부적합 (SPOF 위험·지연)
4. **DB 외 옵션** — Redis `INCR`도 ticket server 패턴의 변형. 더 빠르지만 persistence 결정 필요 (RDB vs AOF)
5. **failover 설계 필수** — ticket server 죽으면 신규 데이터 0. health check + 자동 promotion (이중화 시) 또는 명시적 운영 절차

## 다른 개념과의 관계

- [[unique-id-generation-in-distributed-systems]] — 본 페이지를 포함한 4가지 접근의 비교 총론
- [[multi-master-id-replication]] — ticket server를 다중화하면 사실상 같은 패턴
- [[snowflake-id]] — ticket server의 SPOF·처리량 한계를 모두 해결
- [[single-point-of-failure]] (ch01) — ticket server의 핵심 약점이 SPOF — ch01의 회피 패턴 적용 검토 (이중화·자동 promotion)

## 등장 사례

- ch07 — 분산 unique ID 4 후보 중 하나, snowflake에 밀려 채택 X
- **Flickr** (2010) — 사진 ID에 사용 ([Flickr engineering blog](http://code.flickr.net/2010/02/08/ticket-servers-distributed-unique-primary-keys-on-the-cheap/) ch07 reference [2])
- **Redis INCR 기반 ID 발급기** — ticket server의 in-memory 변형. 매우 흔함
- 일부 ORM·라이브러리 (특히 Python·Ruby) — DB의 sequence 기능을 wrapping해서 같은 패턴 제공
- 사내 admin·운영 도구 — 처리량 낮고 단순함이 핵심인 컨텍스트

## 면접 관점 메모

ch07 4 옵션 중 "**가장 단순한**" 답. "복잡한 거 다 빼고 단순하게"라 답하고 싶을 때 ticket server 꺼냄. 단 면접관이 "SPOF는?" 물으면 immediately 인정하고 snowflake로 넘어가야. Flickr 사례 인용 가치 있음 (대규모 서비스도 한때 이걸로 시작).
