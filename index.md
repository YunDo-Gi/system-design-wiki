# System Design Wiki — Index

> Alex Xu, *System Design Interview 2nd ed.* 기반 개인 위키
> 마지막 갱신: 2026-05-19 (ch05 ingest)

## Chapters (진도)

- [x] [[ch01-scale-zero-to-millions]] — 0에서 수백만 사용자까지의 점진적 확장 서사
- [x] [[ch02-back-of-the-envelope-estimation]] — 데이터 단위·지연 수치·SLA로 면접 추정하기
- [x] [[ch03-framework-for-interviews]] — 시스템 설계 면접 4단계 프로세스
- [x] [[ch04-rate-limiter]] — 처리율 제한 장치 설계 (알고리즘 5종·분산 이슈)
- [x] [[ch05-consistent-hashing]] — 일관된 해싱과 hash ring·virtual nodes
- [ ] ch06 — (미 ingest)

## Concepts (개념)

- [[availability-sla-nines]] — 가동률과 다운타임 환산, SLA (ch02)
- [[back-of-the-envelope-estimation]] — 면접용 용량·QPS·스토리지 추정법 (ch02)
- [[caching-strategies]] — read-through·TTL·eviction·일관성·SPOF 회피 (ch01)
- [[consistent-hashing]] — hash ring·시계방향 lookup·virtual nodes (ch05)
- [[database-replication]] — master/slave 복제로 읽기 분산·가용성 (ch01)
- [[decoupling-with-message-queue]] — producer/consumer 비동기 분리 패턴 (ch01)
- [[fixed-window-counter-algorithm]] — 고정 윈도우 카운터 (rate limit) (ch04)
- [[four-step-interview-framework]] — 면접 4단계 절차·시간 배분·Dos/Don'ts (ch03)
- [[latency-numbers]] — Jeff Dean의 지연 시간 표와 자릿수 감각 (ch02)
- [[leaking-bucket-algorithm]] — 누출 버킷 (FIFO, 평탄 outflow) (ch04)
- [[multi-data-center]] — geoDNS 라우팅·DC간 데이터 동기화 (ch01)
- [[power-of-two-data-units]] — KB/MB/GB/TB/PB 환산 기초 (ch02)
- [[rate-limiting]] — 처리율 제한 총론·위치·hard/soft·OSI (ch04)
- [[sharding]] — DB 수평 분할·sharding key·hotspot/resharding 문제 (ch01)
- [[single-point-of-failure]] — SPOF 정의와 회피 패턴 모음 (ch01)
- [[sliding-window-counter-algorithm]] — 슬라이딩 윈도우 카운터 하이브리드 (ch04)
- [[sliding-window-log-algorithm]] — 슬라이딩 윈도우 로그 (정확·고메모리) (ch04)
- [[stateless-web-tier]] — 세션 외부화로 sticky session 회피 (ch01)
- [[token-bucket-algorithm]] — 토큰 버킷 (버스트 허용, AWS/Stripe) (ch04)
- [[vertical-vs-horizontal-scaling]] — scale up vs scale out 트레이드오프 (ch01)

## Tech (기술)

- [[api-gateway]] — microservices 단일 진입점·rate limit/auth 미들웨어 (proxy, ch04)
- [[cdn]] — 정적 자산 엣지 캐싱, TTL·invalidation·versioning (cdn, ch01)
- [[dns]] — 도메인 해석, geoDNS, TTL (proxy, ch01)
- [[load-balancer]] — 트래픽 분산·failover의 정문 컴포넌트 (proxy, ch01)
- [[memcached]] — 분산 in-memory key-value 캐시 (cache, ch01)
- [[message-queue]] — 비동기 메시지 미들웨어 (queue, ch01)
- [[nosql-database]] — key-value/graph/column/document 4계열 (db, ch01)
- [[redis]] — 풍부한 자료구조·원자 연산·TTL의 in-memory store (cache, ch04)
- [[relational-database]] — RDBMS / SQL / join 기반 (db, ch01)

---

## 갱신 규칙

LLM은 ingest/query/lint 후 본 파일을 갱신한다. 각 항목 포맷:

```
- [[slug]] — 한 줄 요약 (등장 챕터)
```

가나다순(한글)·알파벳순(영문) 혼합 정렬은 카테고리 안에서 LLM이 판단.
