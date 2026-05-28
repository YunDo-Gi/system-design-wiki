---
type: tech
category: db
sources: [ch11]
---

# Graph Database

## 한 줄 정의

데이터를 **노드(node)와 엣지(edge·관계)**로 저장하고, 관계 탐색(traversal)을 1급 연산으로 다루는 데이터베이스. 친구 관계·추천처럼 "연결" 자체가 질의 대상인 도메인에 특화된다 (ch11, p.172). 대표: Neo4j.

## 주요 특성

- **노드 + 엣지 + 속성**: 엔티티(사용자)와 관계(친구·팔로우)를 동등하게 1급으로 모델링.
- **관계 탐색이 상수에 가까움**: 인접 노드로의 이동이 포인터 따라가기(index-free adjacency)라 깊은 관계 질의에서 join보다 빠름.
- **질의 언어**: Cypher(Neo4j) 등 그래프 패턴 매칭 전용 언어.

## 언제 선택하는가 / 대안 비교

| 후보 | 친구 관계 질의 | friend-of-friend(2-hop+) | 비고 |
|---|---|---|---|
| **Graph DB** | 자연스러움 | **빠름**(탐색 최적화) | 관계가 핵심일 때 |
| [[relational-database]] | 가능(join 테이블) | **느림**(다중 self-join) | 관계 얕고 트랜잭션 중심일 때 |
| [[nosql-database]] (document/KV) | 비효율 | 어려움 | 관계가 부차적일 때 |

핵심 판단: **질의의 깊이**. 1-hop(직접 친구)까진 RDB join도 견디지만, friend-of-friend·추천처럼 **다단계 관계 탐색**이 잦으면 graph DB가 압도적. 반대로 관계가 얕고 거래·집계가 본질이면 RDB/NoSQL이 운영·생태계 면에서 낫다.

## 전형적 사용 사례

- 소셜 그래프: 친구·팔로우 관계, friend-of-friend 추천.
- 추천 엔진: "이 상품을 산 사람이 함께 본 상품".
- 사기 탐지: 계좌·거래 네트워크의 이상 패턴.
- 지식 그래프·권한 그래프.

## 실무 함정

- **확장성**: 그래프는 자연스러운 샤딩이 어렵다(관계가 파티션을 가로지름). 초대형 소셜 그래프는 graph DB 대신 커스텀 분산 저장(예: Facebook TAO)을 쓰기도 한다.
- 피드 시스템에서 graph DB는 **친구 ID 조회 소스**로만 쓰고, 실제 fanout/피드는 캐시·큐로 처리하는 식으로 역할을 한정하는 게 보통.
- 쓰기 무거운 분석성 그래프 질의는 OLTP 경로와 분리.

## 등장 사례

- ch11 — fanout service가 친구 ID를 graph DB에서 조회 ([[fanout]])
- Neo4j — friend-of-friend 추천의 교과서 예시 (ch11 reference)
- Facebook TAO — 소셜 그래프 전용 분산 저장(graph DB의 확장 한계를 우회한 사례)
