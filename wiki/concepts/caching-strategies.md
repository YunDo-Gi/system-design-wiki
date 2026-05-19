---
type: concept
tags: [cache, performance]
sources: [ch01]
---

# 캐싱 전략 (Caching Strategies)

## 한 줄 정의

비용이 큰 응답이나 자주 접근되는 데이터를 빠른 메모리 계층에 임시 저장해 후속 요청을 가속하는 일반 기법 (ch01, p.22).

## 왜 필요한가

매 요청마다 DB를 치면 애플리케이션 성능이 DB I/O에 묶인다. 캐시는 DB 부하를 낮추고 응답 지연을 줄인다. DB와 별도의 **캐시 tier**로 분리하면 독립적으로 확장 가능 (ch01, p.22).

## 핵심 메커니즘

**Read-through 패턴** (책 본문 기본 예시, ch01, p.22):

1. web server가 캐시 조회.
2. **hit**: 캐시 값 반환.
3. **miss**: DB 조회 → 캐시에 적재 → 반환.

[[memcached]] 같은 in-memory store가 전형적. 그 외 write-through, write-behind 등 다양한 전략이 있다.

## 사용 시 고려사항 (ch01, p.23)

- **언제 캐시할까**: read 많고 write 적은 데이터. 캐시는 휘발성이므로 중요한 데이터는 영속 저장소에 함께.
- **만료 정책 (expiration/TTL)**: 너무 짧으면 DB 재조회 빈발, 너무 길면 stale.
- **일관성 (consistency)**: 캐시와 DB 변경이 한 트랜잭션이 아니므로 어긋날 수 있음. 멀티 리전에서 특히 어려움 (참고: "Scaling Memcache at Facebook").
- **장애 완화 (SPOF)**: 단일 캐시 노드는 [[single-point-of-failure]]. 멀티 노드·여러 DC 분산·메모리 오버프로비저닝 권장.
- **축출 정책 (eviction)**: 캐시 가득 차면 비워야 함. **LRU**(가장 오래 안 쓴 것)가 가장 일반적, LFU/FIFO도 상황에 따라.

## 트레이드오프

- 빠른 응답·DB 부하 감소 ↔ 일관성 관리 비용, 추가 인프라.
- 캐시 적중률(hit rate)이 낮으면 오히려 지연이 추가될 수 있다.

## 등장 사례

- ch01 — [[database-replication]] 이후, [[cdn]] 도입 직전 단계로 등장. 이후 [[stateless-web-tier]]에서 세션 저장소로 [[memcached]]·Redis가 다시 등장한다.
