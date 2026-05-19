---
type: concept
tags: [database, scalability, partitioning]
sources: [ch01]
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

## 등장 사례

- ch01 — 점진적 확장 서사의 **마지막 단계**. cache·CDN·무상태·멀티 DC·메시지 큐를 다 적용한 뒤에 등장. 이후 [[consistent-hashing]] (ch05)으로 resharding을 정교화한다.
