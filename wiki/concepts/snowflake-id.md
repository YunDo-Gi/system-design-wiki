---
type: concept
tags: [distributed-systems, unique-id, algorithm]
sources: [ch07]
---

# Snowflake ID (Twitter Snowflake)

## 한 줄 정의 / 동기

**64-bit unique ID를 timestamp + 위치 식별 + 순번의 4 섹션으로 분할 생성**하는 알고리즘. Twitter가 2010년 공개. "**Divide and conquer**" 원리 — ID를 한 번에 만들지 말고 의미 있는 섹션으로 나눠 각 섹션을 다른 출처에서 생성 (ch07, p.114).

분산 환경에서 **서버 간 조정 없이 unique + 시간순 정렬 가능 + 64-bit 정수** 한꺼번에 만족시키는 게 핵심 가치. [[uuid]](128-bit·시간순 X), [[multi-master-id-replication]](DC 확장 어려움), [[ticket-server]](SPOF)의 약점을 모두 해결.

## 동작

### 비트 분할

```
┌─┬───────────────────────────────────────┬─────────┬─────────┬─────────────┐
│0│         timestamp (41 bits)           │ dc (5)  │ mc (5)  │   seq (12)  │
└─┴───────────────────────────────────────┴─────────┴─────────┴─────────────┘
  └────────────────────── 64 bits ──────────────────────────────────────────┘

  sign bit │ ms since epoch │ datacenter ID │ machine ID │ sequence per ms
```

| 섹션 | 비트 | 의미 | 출처 |
|---|---:|---|---|
| sign | 1 | 항상 0 (signed integer 호환) | 고정 |
| timestamp | **41** | 커스텀 epoch 이후 millisecond | 시스템 시각 (`now() - epoch`) |
| datacenter ID | 5 | 데이터센터 식별자 | **시작 시 고정** (config) |
| machine ID | 5 | 같은 DC 안 머신 식별자 | **시작 시 고정** (config) |
| sequence | 12 | 같은 ms 안 순번 | **요청마다 increment, ms 바뀌면 0** |

### 생성 의사코드

```
function next_id():
    now_ms = current_time_ms()

    if now_ms == last_timestamp:
        sequence = (sequence + 1) & 0xFFF   # 12-bit mask
        if sequence == 0:                    # 4096개 다 썼음
            now_ms = wait_until_next_ms(last_timestamp)
    else:
        sequence = 0

    last_timestamp = now_ms
    elapsed = now_ms - CUSTOM_EPOCH

    return (elapsed << 22) | (datacenter_id << 17) | (machine_id << 12) | sequence
```

핵심 동작:
- **timestamp는 ms 단위** — 같은 ms 내 여러 요청은 sequence로 구분
- **sequence는 ms 경계에서 0으로 리셋** — 다음 ms엔 처음부터
- **ms 안에 4096개 초과** 시 다음 ms까지 대기 (busy-wait)

### 예시 변환 (ch07, p.116 Figure 7-7)

```
binary: 0-00100010101001011010011011100010110101100-01010-01100-000000000000
        ↑ sign           ↑ timestamp                    ↑ dc   ↑ mc   ↑ seq

timestamp section = 297616116568 (decimal)
+ Twitter epoch (1288834974657)
= 1586451091225 ms
= Apr 09 2020 16:51:31 UTC
```

## 파라미터 · 튜닝 포인트

| 파라미터 | 기본값 | 의미 | 튜닝 시 |
|---|---|---|---|
| `CUSTOM_EPOCH` | 1288834974657 (Twitter epoch, 2010-11-04) | timestamp 0의 의미. 자유롭게 정할 수 있음 | 늦게 둘수록 41-bit timestamp의 사용 가능 연수 ↑ (= 미래 더 오래 씀) |
| timestamp bits (41) | 41 | ms 표현 비트. 41bit = ~69년 | bits ↑ → 더 오래 작동, but dc/seq 비트 ↓ |
| datacenter ID bits (5) | 5 = 32 DC | DC 개수 한도 | 글로벌 서비스라면 늘림 |
| machine ID bits (5) | 5 = 32 머신/DC | DC당 머신 한도 | 한 DC당 머신 많으면 늘림 |
| sequence bits (12) | 12 = 4096/ms | ms당 ID 생성 한도 | 더 많은 처리량 필요 시 ↑ (하지만 timestamp 줄여야) |

**기본 비트 분할의 합리성** (ch07, p.117 추가 토픽):
- 41-bit timestamp = **~69년 작동** (2^41 / 1000 / 365 / 24 / 3600 ≈ 69.7)
- 12-bit sequence = **ms당 4096개 = 머신당 초당 ~409만 ID** — 책의 요구사항(10K/s)을 훨씬 초과
- 5-bit DC + 5-bit machine = **최대 1024 머신 동시 생성**

→ 보통 변경 안 함. Twitter 기본값 그대로 쓰는 경우 多.

## 트레이드오프

### Pros

- **Coordination-free** — 머신끼리 통신 없이 독립 생성 (DC/machine ID는 시작 시 고정)
- **시간순 정렬** — timestamp가 가장 상위 비트라 ID 숫자 비교가 시간 비교
- **64-bit 정수** — DB index 효율적 ([[uuid]]의 128-bit보다 절반)
- **고처리량** — 머신당 ms당 4096개 = 초당 ~409만
- **분산 확장 자연** — DC/machine 늘리면 그만큼 처리량 ↑

### Cons

- **시각 동기화 의존성** — 시계가 뒤로 가면 ID 충돌·역순. NTP 필수 ([[network-time-protocol]])
- **머신 ID 관리** — 시작 시 unique한 DC+machine ID 배정 필요. 휴먼 에러 시 ID 충돌 (ch07: "*Any changes in datacenter IDs and machine IDs require careful review*")
- **시계 되돌림(clock drift) 위험** — leap second·NTP 보정·VM 재시작 등으로 시계가 뒤로 가면 같은 timestamp 재사용 → 충돌. snowflake 변형판들(Sonyflake 등)이 별도 처리
- **DC당 32 머신 한계** (기본 비트 분할) — 더 필요하면 비트 재할당
- **69년 후 wrap-around** — custom epoch 옮기거나 비트 늘려야

### 언제 쓰고 언제 안 쓰는가

**쓰는 게 자연스러운 경우**:
- 분산 환경에서 unique ID 필요 (DB primary key, 메시지 ID, 트랜잭션 ID)
- 시간순 정렬이 중요 (timeline·feed·로그)
- 64-bit 정수가 필요 (DB·인덱스 효율, 모바일 클라이언트 호환)
- 처리량 높음 (수만/s 이상)

**다른 답이 나을 수 있는 경우**:
- 머신이 시각 동기화 안 됨 → [[uuid]] (시계 무관)
- 처리량 낮고 단순 → [[ticket-server]] (Flickr 패턴)
- 비밀번호 reset token 등 **예측 불가능해야 하는 ID** → snowflake는 예측 가능(timestamp 노출) → cryptographic random
- ID에서 머신·DC 정보 노출이 보안 문제 → 마스킹 또는 다른 알고리즘

## 다른 알고리즘과의 위치

ch07이 비교한 4가지 ([[unique-id-generation-in-distributed-systems]] 총론 참조):

| 방식 | unique | 시간순 | 64-bit | 분산 | 비고 |
|---|---|---|---|---|---|
| auto_increment | ✅ | ✅ | ✅ | ❌ | 단일 DB. 분산 안 됨 |
| [[multi-master-id-replication]] | ✅ | ❌ | ✅ | 부분적 | DC 확장 어려움 |
| [[uuid]] | ✅ | ❌ | ❌ (128bit) | ✅ | 시간순 X, 길이 2배 |
| [[ticket-server]] | ✅ | ✅ | ✅ | ❌ | SPOF |
| **Snowflake** | ✅ | ✅ | ✅ | ✅ | **모두 만족** |

ch07의 결론: "*We settle on snowflake as it supports all our use cases and is scalable in a distributed environment*" (p.117).

## 실무 적용 시 고려사항

1. **시계 동기화 인프라 먼저** — NTP 환경 없이 snowflake 쓰면 충돌 위험. AWS는 NTP 서버 제공, 자체 데이터센터면 NTP 서버 운영 필요. ch04 §"분산 환경 - Synchronization"과 같은 맥락
2. **DC/Machine ID 발급 자동화** — 휴먼 설정 실수 = ID 충돌. ZooKeeper·etcd 같은 coordinator로 시작 시 동적 발급하는 패턴 흔함 (예: Sonyflake)
3. **시계 되돌림 방어** — `last_timestamp > now_ms`면 거부하거나 마지막 시각까지 대기. 운영 가능한 snowflake 구현 (Twitter 원본 + Sonyflake·Snowflake4s 등 fork)이 모두 이 분기 가짐
4. **비트 분할 변경은 신중** — 한 번 ID를 발급하기 시작하면 비트 분할 변경 = 기존 ID와 충돌 가능. 변경하려면 epoch도 같이 옮겨야
5. **High availability 미션 크리티컬** — ID generator가 죽으면 모든 신규 데이터 생성 중단. 보통 머신 여러 대에 분산 (각자 다른 machine ID)
6. **`secrets.token_urlsafe` 같은 random ID와의 비교** — random은 충돌 가능성 0%는 아님 (birthday paradox). knot의 단축 코드처럼 작은 키 공간이면 snowflake 같은 결정적 방식이 안전

## 등장 사례

- ch07 — Twitter snowflake 원형 알고리즘으로 채택
- Twitter — 자체 트윗 ID에 사용 (10년+ 운영)
- Discord — 메시지 ID에 변형 사용 (Twitter epoch을 Discord epoch으로)
- Instagram — 비슷한 64-bit 분산 ID 사용 (timestamp + shard + sequence)
- Sonyflake — Sony의 snowflake 변형 (Go 구현). DC ID bit 줄이고 timestamp 10ms 단위로 늘림
- knot — `secrets.token_urlsafe(6)` (mock) → snowflake 또는 base62 encoding으로 교체 가능 (ch08 URL shortener 진화 시)

## 면접 관점 메모

- 64-bit unique ID 요구사항이 나오면 "분산 환경이면 snowflake가 표준"이라 답할 수 있어야. 비트 분할 외워두면 즉시 풀이 가능
- "왜 UUID 안 쓰나?" → 128-bit + 시간순 X. "왜 ticket server 안 쓰나?" → SPOF. **각 대안의 약점**을 알아야 snowflake 선택 정당화 가능
