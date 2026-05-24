---
type: concept
tags: [distributed-systems, unique-id, database]
sources: [ch07]
---

# Multi-master ID Replication (auto_increment with step)

## 한 줄 정의

**여러 master DB가 각각 `auto_increment` step을 다르게 두어** 서로 충돌하지 않는 ID를 생성하는 패턴. 예: 서버 1은 1,3,5,...; 서버 2는 2,4,6,... ch07이 분산 unique ID의 4가지 후보 중 하나로 평가 (ch07, p.112).

## 왜 필요한가

단일 DB `auto_increment`의 자연 확장. 분산 환경으로 가야 할 때 가장 "**친숙한 SQL 그대로**" 풀고 싶은 시도. 별도 알고리즘·코디네이터 없이 DB 기능만으로 분산 ID.

## 핵심 메커니즘

### Step 분할

서버 수 `k`라면 각 서버의 `auto_increment_increment`를 `k`로 설정. 시작점(`auto_increment_offset`)을 각자 다르게:

```
N개 서버 운영:
  서버 1: offset=1, step=N → 1, N+1, 2N+1, ...
  서버 2: offset=2, step=N → 2, N+2, 2N+2, ...
  ...
  서버 N: offset=N, step=N → N, 2N, 3N, ...
```

MySQL 예시:
```sql
SET auto_increment_increment = 2;
SET auto_increment_offset = 1;     -- 서버 1
-- 다른 서버에선 offset = 2
```

### 작동 방식 (ch07, p.112 Figure 7-2)

```
MySQL master 1 ─→ ID: 1, 3, 5, 7, ...  ─┐
                                          ├→ web servers
MySQL master 2 ─→ ID: 2, 4, 6, 8, ...  ─┘
```

각 master가 독립 발급. 같은 ID 발급 불가능 (offset/step 보장).

## 트레이드오프

### Pros

- **SQL 표준** — 익숙. 별도 알고리즘·라이브러리 불필요
- **단순 운영** — 새 서버 추가 시 step·offset만 조정
- **64-bit fit** — DB의 BIGINT (8 byte)
- **숫자 ID**

### Cons (ch07이 명시한 단점)

ch07 p.112: "*Major drawbacks*":

1. **DC 확장 어려움** — DC를 추가하면 전체 step 재계산 + 모든 DB의 설정 변경. 운영 중에 위험
2. **시간순 정렬 어긋남** — IDs do not go up with time across multiple servers. 서버 1이 빠르면 1,3,5,7,...; 서버 2가 느리면 100,102,104,... — 같은 시각에 발급된 ID 비교 불가
3. **서버 추가/제거 시 확장 어려움** — 기존 ID 보존하면서 step 바꾸는 게 까다로움

추가 단점:
- **master 노드 1개당 처리량 한계** — auto_increment는 결국 DB 락. 머신당 처리량 ↓
- **DB 종속** — MySQL 변종 외엔 같은 패턴 안 통할 수 있음

## 다른 알고리즘과의 위치

| | multi-master | UUID | ticket server | snowflake |
|---|---|---|---|---|
| 분산 | 부분적 (DC 추가 어려움) | ✅ | ❌ (SPOF) | ✅ |
| 시간순 | **❌** | ❌ | ✅ | ✅ |
| 64-bit | ✅ | ❌ (128bit) | ✅ | ✅ |
| 처리량 | 중 (DB 락) | 높음 (random) | 낮음 (SPOF 병목) | 높음 |
| 운영 복잡도 | 중 (config 동기화) | 낮음 | 낮음 | 중 (DC/machine ID 관리) |

→ ch07이 multi-master를 채택 안 한 이유: **시간순 정렬 X + DC 확장 어려움**. snowflake에 모두 밀림.

## 실무 적용 시 고려사항

1. **N을 미리 충분히 크게 설정** — 운영 중 N 변경은 매우 위험. 처음에 N=100 정도로 두면 100 서버까지 자연 확장. 단 ID 공간 효율은 ↓
2. **failover 시 ID 보장** — 서버 1이 죽고 서버 1' 로 교체될 때 같은 offset/step 유지 필수. 아니면 충돌 가능
3. **시간순 의존하는 코드 안 만들기** — primary key 정렬이 생성 시각 정렬이라 가정하면 안 됨
4. **소규모·내부 시스템에 적합** — 글로벌 분산·다지역 서비스엔 부적합 (DC 확장 약점)

## 다른 개념과의 관계

- [[unique-id-generation-in-distributed-systems]] — 본 페이지를 포함한 4가지 접근의 비교 총론
- [[snowflake-id]] — multi-master의 약점(시간순·DC 확장)을 모두 해결한 대안
- [[ticket-server]] — multi-master 정반대 (중앙 집중)
- [[database-replication]] (ch01) — master/slave는 read scaling. multi-master는 ID 생성 scaling이 목적, 다른 문제

## 등장 사례

- ch07 — 분산 unique ID 4 후보 중 하나, snowflake에 밀려 채택 X
- **MySQL 기반 레거시 시스템** — 2000년대 초중반 분산 MySQL 셋업에서 자주 사용
- 일부 ORM 또는 sharded MySQL 셋업이 내부적으로 이 패턴 적용 (사용자는 모르고 씀)
- 최근에는 대부분 [[snowflake-id]] 또는 application-level ID 발급으로 대체됨

## 면접 관점 메모

"분산 환경에서 unique ID"라는 질문이 나왔을 때 **가장 먼저 떠올라야 하는 naive 답**이 multi-master. 그 후 "왜 부족한지(시간순·DC 확장)"를 짚고 snowflake로 넘어가는 게 자연 흐름. multi-master 자체를 모르면 비교가 약해짐.
