---
type: concept
tags: [database, scalability, partitioning]
sources: [ch01, ch09, ch11, ch13, ch14]
---

# 샤딩 (Sharding)

## 한 줄 정의

큰 DB를 동일 스키마·다른 데이터를 가진 작은 조각(shard)들로 수평 분할해 쓰기·저장 용량을 확장하는 기법 (ch01, p.35).

## 왜 필요한가

[[database-replication]]은 읽기를 분산할 뿐 **쓰기와 저장 용량은 master 한 대에 묶여 있다**. 데이터가 일정 규모를 넘으면 [[vertical-vs-horizontal-scaling]]의 vertical 한계에 부딪치므로 DB 자체를 수평 분할해야 한다.

## 핵심 메커니즘

- **샤드 키(sharding key / partition key)** 를 정한다. 예: `user_id`.
- 해시 함수로 데이터를 특정 shard에 배치. 책 예시는 `user_id % 4` → shard 0~3 (ch01, p.35-36).
- 애플리케이션은 쿼리 시 같은 함수로 해당 shard로 라우팅.
- 좋은 sharding key는 **데이터를 고르게 분산**시키는 키여야 한다.

## 트레이드오프 — 주의해야 할 새 문제 (ch01, p.36)

- **Resharding**: 한 shard가 가득 차거나, 트래픽이 불균등해지면 shard 수를 바꿔야 함. 데이터 이동 비용 큼 → [[consistent-hashing]]이 흔한 해법 (ch05에서 다룸).
- **Celebrity / hotspot 문제**: 특정 키(예: Katy Perry, Justin Bieber)의 데이터가 한 shard에 몰려 read 폭주. 해당 키는 전용 shard로 분리하거나 추가 분할.
- **Join 어려움**: 여러 shard에 걸친 join은 비싸거나 불가. 흔히 **비정규화(de-normalization)** 로 한 테이블에서 처리 가능하게 만든다.
- 운영 복잡도 증가: 백업·스키마 변경·트랜잭션 모두 어려워진다.

## 샤딩 전략 비교

| 전략 | 분산 방식 | 장점 | 함정 |
|---|---|---|---|
| **Hash-based** | `hash(key) % N` | 균등 분포 | resharding 시 키 대부분 이동 ([[consistent-hashing]]이 해결) |
| **Range-based** | 키 범위 구간별 | 범위 쿼리 효율 | 시간 키 등에서 hot shard 발생 |
| **Directory-based** | 별도 lookup 테이블 | 유연, 마이그레이션 자유 | lookup 서비스가 새 SPOF |
| **Geo-based** | 지역별 | 지역 가까이 데이터 보관 | 사용자 이동·글로벌 집계 어려움 |

## 실무 적용 시 고려사항

- **샤드 키 선택은 사실상 되돌리기 어려움**: 한 번 정하면 변경에 막대한 데이터 이동 비용. 후보 키를 **cardinality(고유값 수), 분포 균등성, 쿼리 패턴 적합성** 3축으로 평가.
- **Cross-shard 쿼리 회피 설계**: 동일 사용자/주문/조직의 데이터를 같은 샤드에 두는 **공통 prefix** 전략. 글로벌 집계는 별도 OLAP 시스템(데이터 웨어하우스)으로.
- **트랜잭션은 단일 샤드로**: 분산 트랜잭션(2PC)는 비싸고 잠금이 길어 보통 회피. 여러 샤드 걸친 트랜잭션은 **saga 패턴** 또는 **eventual consistency + 보상 트랜잭션**.
- **운영의 N배 증가**: 백업·DDL·복구·모니터링 모두 N배. **자동화 없이는 운영 폭주**. 보통 vitess, citus, 또는 MongoDB sharded cluster 같은 운영 자동화 솔루션 위에 얹는다.
- **Celebrity / hot shard 대응**: 핫스팟이 발견되면 ① 해당 키 데이터를 여러 샤드에 복제 ② 일부 쓰기는 큐로 비동기 처리 ③ in-memory 캐시로 read 흡수. 단순히 샤드를 늘리는 것만으론 해결 안 됨.
- **샤딩은 최후의 수단**: 캐싱, 읽기 분산, 비정규화, 부분 sharding(특정 큰 테이블만) 등을 먼저 시도. 운영 복잡도 비용이 크다.

## 등장 사례

- ch01 — 점진적 확장 서사의 **마지막 단계**. cache·CDN·무상태·멀티 DC·메시지 큐를 다 적용한 뒤에 등장. 이후 [[consistent-hashing]] (ch05)으로 resharding을 정교화한다.
- Stripe, Discord, Pinterest 등 — 대규모 OLTP에서 application-level sharding 적용 사례가 잘 알려져 있다.
