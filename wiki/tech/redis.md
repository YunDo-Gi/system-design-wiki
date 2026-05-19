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

## 전형적 사용 사례

- **카운터·rate limiting**: `INCR` + `EXPIRE`. ch04 high-level architecture(Figure 4-12)의 핵심.
- **분산 락·원자 연산**: Lua 스크립트로 read-check-increment 원자화 → ch04 race condition 해법.
- **Sorted set으로 sliding window log**: 타임스탬프를 score로, 윈도우 밖 요소를 `ZREMRANGEBYSCORE`로 일괄 제거.
- 세션 저장소 ([[stateless-web-tier]] 옵션), pub/sub 메시지, 리더보드.

## ch04에서의 활용

- 단순 한도: `INCR key` → 1 → 임계치 비교 → `EXPIRE key window_size`.
- 정확 한도 (sliding window log): sorted set에 timestamp를 score로 ZADD, 윈도우 밖 ZREMRANGEBYSCORE, ZCARD로 카운트.
- 다중 rate limiter 서버 간 **중앙 공유 스토어** 역할 — sticky session 대신 채택되는 표준 패턴 (ch04, p.72).

## 등장 사례

- ch04 — high-level 아키텍처와 분산 race condition 해법 양쪽에서 등장.
- 이전 챕터들에서는 [[caching-strategies]]·[[stateless-web-tier]] 옵션으로 [[memcached]]와 함께 언급. 후속 챕터(특히 ch06 key-value store)에서 자료구조·일관성 모델이 다시 비교된다.
