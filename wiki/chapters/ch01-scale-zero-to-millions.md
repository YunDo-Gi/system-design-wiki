---
chapter: 1
title_en: Scale From Zero to Millions of Users
title_ko: 0에서 수백만 사용자까지의 확장
ingested_at: 2026-05-19
---

# Scale From Zero to Millions of Users

## 핵심 takeaway

- 시스템 확장은 **단일 서버 → web/data tier 분리 → DB 복제 → 캐시·CDN → 무상태 web tier → 멀티 DC → 메시지 큐 → DB 샤딩** 순으로 진화한다 (ch01, p.16-37).
- **수평 확장이 대규모의 정답**: vertical scaling은 하드웨어 상한·SPOF·고비용 문제로 큰 트래픽에 부적합 (ch01, p.18).
- **무상태 web tier**가 오토스케일링·복원력의 전제. 세션·이미지 같은 상태는 공유 저장소(DB/Memcached/Redis/NoSQL)로 빼고, sticky session은 운영 부담이 크므로 피한다 (ch01, p.27-29).
- **캐시·CDN·메시지 큐는 디커플링 도구**. 캐시는 DB 부하, CDN은 정적 자산 지연, 큐는 producer/consumer 결합도를 낮춘다 (ch01, p.22-26, p.34).
- **백만 사용자 청사진 7원칙**: 무상태 web tier / 모든 tier 이중화 / 가능한 만큼 캐시 / 멀티 데이터센터 / CDN으로 정적 자산 / 데이터 tier 샤딩 / 서비스 분리 + 모니터링·자동화 (ch01, p.37).

## 본문 요약

장은 가상의 웹사이트가 사용자 1명에서 수백만 명으로 성장하는 시나리오를 따라간다.

**1) 단일 서버**: 웹·DB·캐시가 한 호스트에 동거. 사용자 증가 시 **web tier와 data tier를 분리**(Figure 1-3)하여 독립 확장 가능 상태로 만든다. DB 선택은 RDBMS(MySQL·PostgreSQL 등)를 기본으로 하되, 초저지연·비정형·대용량·직렬화 위주라면 NoSQL(key-value/graph/column/document)을 고려 (ch01, p.13).

**2) 수평 확장 시작**: vertical은 한계가 명확하므로 [[vertical-vs-horizontal-scaling]]에서 horizontal로 전환. web tier 앞에 [[load-balancer]]를 두어 failover와 트래픽 분산 확보. DB는 [[database-replication]] (master/slave)로 읽기 분산·신뢰성·고가용성 확보 (ch01, p.18-21).

**3) 성능 개선 레이어**: [[caching-strategies]] (read-through, expiration, eviction)로 DB 부하 완화 (ch01, p.22). 정적 자산은 [[cdn]]으로 옮겨 지리적 지연을 줄인다 (ch01, p.24-26). 캐시 단일 노드는 [[single-point-of-failure]]가 되므로 멀티 노드·오버프로비저닝.

**4) 무상태 web tier**: [[stateless-web-tier]]로 만들어야 오토스케일링이 가능. 세션을 공유 저장소로 이동 (ch01, p.27-29).

**5) 글로벌화**: [[multi-data-center]] (geoDNS 라우팅, 비동기 복제, 자동 배포)로 가용성·지연 개선 (ch01, p.31-33).

**6) 비동기화**: 사진 처리 같은 무거운 작업은 [[decoupling-with-message-queue]]로 분리. producer/consumer 독립 스케일 (ch01, p.34). 로깅·메트릭·자동화(CI)는 규모가 커지면 필수.

**7) 데이터 tier 확장**: 결국 vertical scaling 한계에 부딪치므로 [[sharding]]으로 수평 분할. sharding key·resharding·celebrity(hotspot)·join 문제 해결책 필요 (ch01, p.35-36). resharding은 [[consistent-hashing]] (ch05)으로 다룬다.

## 등장 개념

- [[vertical-vs-horizontal-scaling]] — scale up vs scale out 트레이드오프
- [[database-replication]] — master/slave, 읽기 분산, failover
- [[stateless-web-tier]] — 세션 외부화, sticky session 회피
- [[caching-strategies]] — read-through, expiration, eviction, SPOF 회피
- [[sharding]] — 수평 DB 분할, sharding key 선택, hotspot 문제
- [[single-point-of-failure]] — SPOF 정의와 회피
- [[multi-data-center]] — geoDNS, 동기화, 장애 시 트래픽 우회
- [[decoupling-with-message-queue]] — 비동기 분리, 독립 스케일링

## 등장 기술

- [[load-balancer]] — 트래픽 분산·failover의 기본 컴포넌트
- [[cdn]] — 정적 자산 엣지 캐시
- [[memcached]] — 책 본문에서 API까지 인용한 대표 분산 캐시
- [[relational-database]] — 기본 데이터 tier 선택지
- [[nosql-database]] — 비정형·대용량·초저지연 대안
- [[message-queue]] — 비동기 분리 표준 컴포넌트
- [[dns]] — 도메인 해석, geoDNS

## 면접 관점 메모

- 1장은 컴포넌트 카탈로그가 아니라 **"언제 무엇을 도입하는가"의 순서 감각**을 묻는 장. 면접에서 진화 서사로 풀어내는 게 자연스럽다.
- "왜 sticky session 대신 무상태인가", "왜 샤딩 전에 복제·캐시인가", "캐시 만료 정책을 어떻게 정할 것인가" 같은 후속 질문이 따라붙는다.
- 후속 챕터로의 연결: resharding → [[consistent-hashing]] (ch05), 가용성 수치 → [[back-of-the-envelope-estimation]] (ch02).
