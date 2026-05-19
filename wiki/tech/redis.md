---
type: tech
category: cache
sources: [ch04]
---

# Redis

## 한 줄 정의

다양한 자료구조(string, hash, list, set, sorted set, stream 등)와 영속화·pub/sub·Lua 스크립트를 제공하는 in-memory data store (ch04, p.67).

## 주요 특성

- **In-memory** + 선택적 영속화(RDB snapshot / AOF log). 휘발성이 아닌 운영도 가능.
- **풍부한 자료구조** — [[memcached]]와 가장 큰 차이. 카운터/리더보드/큐/세션 등 다양한 도메인을 단일 노드로 표현 가능.
- **단일 스레드 + 원자적 명령**: 한 명령은 원자적이므로 락 없이 안전한 상태 변경이 가능. 여러 명령을 묶을 땐 **Lua 스크립트**·**MULTI/EXEC**.
- **TTL/EXPIRE**로 시간 기반 자동 만료 — rate limiter 카운터 윈도우 만료에 직접 활용.
- 클러스터 모드로 샤딩, replica로 읽기 확장 ([[database-replication]] 패턴 유사).

## 언제 선택하는가 / 대안 비교

| 후보 | 특성 | Redis 대비 |
|---|---|---|
| **[[memcached]]** | 단순 KV, 멀티스레드, 휘발 | 더 단순·메모리 효율 ↑, 기능 ↓ |
| **Redis** | 자료구조, Lua, 영속화, pub/sub | 범용성·기능 ↑, 운영 복잡도 ↑ |
| **DynamoDB / Bigtable** | 매니지드 KV, 영속, 확장 | TB 단위·내구성 최우선이면 |
| **Aerospike, KeyDB, Dragonfly** | Redis 호환·다른 트레이드오프 | 매우 큰 처리량·다중 코어 |

**Redis 선택 기준**:
- 자료구조(sorted set, hash, stream) 활용.
- TTL·원자 연산이 핵심 (rate limit, 세션, lock).
- 영속화 + 캐시 두 역할 동시.
- 단순 KV만 필요하면 [[memcached]]가 더 가볍다.

## 전형적 사용 사례

- **카운터·rate limiting**: `INCR` + `EXPIRE`. ch04 high-level architecture(Figure 4-12)의 핵심.
- **분산 락·원자 연산**: Lua 스크립트로 read-check-increment 원자화 → ch04 race condition 해법.
- **Sorted set으로 sliding window log**: 타임스탬프를 score로, 윈도우 밖 요소를 `ZREMRANGEBYSCORE`로 일괄 제거.
- 세션 저장소 ([[stateless-web-tier]] 옵션), pub/sub 메시지, 리더보드, 작업 큐, 캐시.

## ch04에서의 활용

- 단순 한도: `INCR key` → 1 → 임계치 비교 → `EXPIRE key window_size`.
- 정확 한도 (sliding window log): sorted set에 timestamp를 score로 ZADD, 윈도우 밖 ZREMRANGEBYSCORE, ZCARD로 카운트.
- 다중 rate limiter 서버 간 **중앙 공유 스토어** 역할 — sticky session 대신 채택되는 표준 패턴 (ch04, p.72).

## 실무 함정

- **메모리 폭주**: in-memory가 본질 — 데이터가 무한 늘면 OOM. **maxmemory** 설정 + **eviction policy** (allkeys-lru, volatile-lru 등) 필수. TTL 누락 키가 가장 흔한 폭주 원인.
- **영속화 트레이드오프**:
  - **RDB snapshot**: 주기적 fork → 큰 인스턴스에서 fork 비용·메모리 2배.
  - **AOF**: 모든 write 로깅 → 디스크 IO 부담, 단 복구 시 데이터 손실 작음.
  - 둘 다 사용하면 안전성 ↑, 비용도 ↑. 캐시 용도면 영속화 끄는 게 보통.
- **단일 스레드의 한계**: O(N) 명령(KEYS, SMEMBERS 대형 set 등)이 전체를 블록. **production에서 KEYS 금지** — 대신 SCAN. 큰 자료구조 한 번에 처리하는 명령 회피.
- **클러스터 모드의 함정**: 클러스터는 cross-slot 트랜잭션·MGET·Lua 사용 시 제약. hash tag `{slot}`로 같은 슬롯에 모으는 설계 필요.
- **Replication lag**: replica로 읽기 분산할 때 stale. 일관성 민감한 read는 master로.
- **백업·운영**: BGSAVE는 fork 비용. AOF rewrite도. 큰 인스턴스(>20GB)는 운영 부담 큼 — 일찍 샤딩 고려.
- **Pub/Sub 신뢰성 없음**: 메시지 손실 가능 (subscriber 다운 시). 신뢰성 필요하면 **Streams** 사용.
- **만료 키 즉시 사라지지 않음**: TTL 만료 후 lazy + 주기적 청소. 메모리 통계와 실제 만료 사이 시차 존재.
- **Lua 스크립트 시간 초과**: 긴 스크립트는 단일 스레드를 블록 → 전체 hang. 짧고 단순하게.

## 등장 사례

- ch04 — high-level 아키텍처와 분산 race condition 해법 양쪽에서 등장.
- 이전 챕터들에서는 [[caching-strategies]]·[[stateless-web-tier]] 옵션으로 [[memcached]]와 함께 언급. 후속 챕터(특히 ch06 key-value store)에서 자료구조·일관성 모델이 다시 비교된다.
