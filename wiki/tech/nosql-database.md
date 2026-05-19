---
type: tech
category: db
sources: [ch01]
---

# NoSQL 데이터베이스 (NoSQL Database)

## 한 줄 정의

관계·SQL·join에 의존하지 않는 비-관계형 DB 계열. 책은 4가지로 분류: **key-value, graph, column, document** (ch01, p.13).

## 주요 특성

- **유연한 스키마**: 비정형·반정형 데이터에 강함.
- **수평 확장 친화**: 분산을 전제로 설계된 제품이 많음(예: Cassandra, DynamoDB) → [[stateless-web-tier]]의 세션 저장소로 자주 선택됨 (ch01, p.30).
- **Join 미지원이 일반적**: 데이터 모델을 미리 정리해두어야 한다.
- 일관성 모델이 다양 — eventual consistency가 흔하다.

대표 제품 (ch01, p.13): CouchDB, Neo4j, Cassandra, HBase, Amazon DynamoDB.

## 책이 제시하는 선택 기준 (ch01, p.13)

NoSQL이 적합한 경우:

- 초저지연이 필요할 때.
- 비정형 데이터, 또는 관계형 모델이 없을 때.
- JSON/XML/YAML 직렬화·역직렬화 위주.
- 매우 큰 데이터 저장.

## 전형적 사용 사례

- 대규모 세션 스토어 ([[stateless-web-tier]]).
- 시계열·로그·이벤트 저장.
- 거대 사용자 그래프·메시지 피드.

## 등장 사례

- ch01 — [[relational-database]]의 한계를 보완하는 옵션으로 도입. [[stateless-web-tier]] 다이어그램(Figure 1-14)에서 세션 저장 옵션으로 다시 등장하며, [[sharding]] 절 말미에선 비관계형 워크로드를 NoSQL로 옮겨 DB 부하를 줄이는 패턴도 소개된다.
