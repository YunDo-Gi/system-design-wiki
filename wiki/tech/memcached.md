---
type: tech
category: cache
sources: [ch01]
---

# Memcached

## 한 줄 정의

분산 in-memory key-value 캐시. 책에서 캐시 tier의 대표 사례로 본문에 API 코드까지 인용되는 컴포넌트 (ch01, p.22).

## 주요 특성

- **휘발성 메모리 저장**: 빠른 read/write, 그러나 재시작 시 데이터 손실 → 영속 저장은 별도 (ch01, p.23).
- **간단한 API**: `set(key, value, ttl)`, `get(key)` 수준 (책 예시 그대로).
- **분산**: 여러 노드로 키 공간 분할(클라이언트 측 해싱). 단일 노드 SPOF는 멀티 노드·여러 DC로 회피.
- **TTL·축출 정책**: 만료 기반 제거 + LRU 기반 축출.
- 비교: **Redis**는 다양한 자료구조·영속화·pub/sub까지 — 책에선 둘을 묶어 "Memcached/Redis"로 자주 언급.

## 전형적 사용 사례

- DB 결과 캐싱(read-through, [[caching-strategies]] 참조).
- [[stateless-web-tier]] 구성에서 세션 저장소.
- 짧은 TTL의 임시 계산 결과 캐싱.

## 등장 사례

- ch01 — 캐시 tier의 기본 예시로 등장 (Figure 1-7, API 코드 예제). 이후 [[stateless-web-tier]] 구성의 세션 저장 옵션으로도 다시 언급. 참고 자료로 Facebook의 "Scaling Memcache at Facebook" 인용.
