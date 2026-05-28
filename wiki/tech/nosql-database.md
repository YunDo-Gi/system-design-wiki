---
type: tech
category: db
sources: [ch01, ch11]
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

## 언제 선택하는가 / 대안 비교

| 계열 | 대표 | 적합 |
|---|---|---|
| **Key-Value** | [[redis]], DynamoDB | 캐시, 세션, 카운터, 단순 lookup |
| **Document** | MongoDB, Couchbase | 반정형 JSON, CMS, 카탈로그 |
| **Wide-column** | Cassandra, HBase, ScyllaDB | 대규모 write 처리, 시계열, 로그 |
| **Graph** | Neo4j, Neptune | 관계 중심 도메인 (소셜, 추천, 사기 탐지) |

**선택 기준**:
- 쿼리 패턴이 단순하고 분명히 정해져 있다 → NoSQL이 강함.
- 트랜잭션·복잡 join이 필수 → [[relational-database]].
- 두 가지 워크로드가 섞이면 **polyglot persistence** (각 워크로드에 다른 DB).

## 전형적 사용 사례

- 대규모 세션 스토어 ([[stateless-web-tier]]).
- 시계열·로그·이벤트 저장.
- 거대 사용자 그래프·메시지 피드.
- 카탈로그·CMS의 유연한 콘텐츠.

## 실무 함정

- **"Schema-less ≠ schema-free"**: 결국 애플리케이션 코드 어딘가에 스키마가 박힌다. 코드가 곧 스키마 ↔ DB에 강제력이 없어 데이터 불일치가 누적. **schema 마이그레이션 도구** 또는 검증 레이어가 결국 필요.
- **쿼리 패턴 먼저 → 데이터 모델**: RDBMS는 모델 먼저 짜고 쿼리 짤 수 있지만, NoSQL은 쿼리 패턴이 모델을 결정. 잘못 잡으면 마이그레이션이 매우 어려움 ("query-driven design").
- **Eventual consistency의 오해**: "잠시 어긋날 뿐"이 아니라 "한참 어긋날 수도 있음". 비즈니스 로직이 이를 견뎌야 함.
- **Join 부재 → 비정규화**: 같은 데이터가 여러 문서·테이블에 복제. 업데이트 시 일관성 유지는 애플리케이션 책임 — 누락이 흔한 버그.
- **트랜잭션 가정 무너짐**: 단일 문서·단일 키 범위에서만 atomicity 보장. 여러 키 트랜잭션은 saga·twoPL·외부 코디네이션 필요.
- **Hot partition**: 키 분포 불균등으로 한 파티션 폭주. 분포 분석·키 prefix 설계 필요. Cassandra의 wide row 안티패턴이 전형.
- **Backup·운영 도구의 미성숙**: 제품·버전마다 운영 도구 격차 큼. 운영 인력의 학습 곡선이 RDBMS보다 가파를 수 있음.
- **Vendor lock-in**: DynamoDB·Firestore 등 매니지드 NoSQL은 마이그레이션이 매우 어려움 (API·쿼리 모델 의존).

## 등장 사례

- ch01 — [[relational-database]]의 한계를 보완하는 옵션으로 도입. [[stateless-web-tier]] 다이어그램(Figure 1-14)에서 세션 저장 옵션으로 다시 등장하며, [[sharding]] 절 말미에선 비관계형 워크로드를 NoSQL로 옮겨 DB 부하를 줄이는 패턴도 소개된다.
