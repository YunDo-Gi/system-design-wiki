---
type: tech
category: db
sources: [ch01]
---

# 관계형 데이터베이스 (Relational Database, RDBMS)

## 한 줄 정의

데이터를 테이블·행·컬럼 형태로 저장하고 **SQL과 join**으로 질의하는 전통적 데이터베이스. MySQL, PostgreSQL, Oracle 등 (ch01, p.13).

## 주요 특성

- **스키마 기반**: 정형 데이터, 강한 타입.
- **ACID 트랜잭션**: 일관성 강함.
- **SQL + join**: 정규화된 데이터 모델에 강함.
- 40여 년의 운영 노하우 — 대부분 사례에서 기본 선택지 (ch01, p.13).
- 한계: 쓰기·저장 용량 수평 확장이 어렵다 → [[database-replication]]으로 읽기 분산, [[sharding]]으로 쓰기 분산. 샤딩 후엔 cross-shard join이 어려워 비정규화(de-normalization)가 흔한 우회책.

## 언제 선택하는가 / 대안 비교

| 측면 | RDBMS | [[nosql-database]] |
|---|---|---|
| 데이터 모델 | 정형, 강한 스키마 | 유연 |
| 트랜잭션 | ACID 완전 지원 | 제한적 |
| Join | SQL로 자유 | 제한 / 불가 |
| 확장 | 복제·샤딩 (수동) | 수평 확장 친화 |
| 운영 노하우 | 풍부 | 제품마다 학습 |
| 일관성 모델 | strong | eventual이 흔함 |

**RDBMS를 기본으로 선택**, 다음 조건에서 NoSQL 고려: 초저지연 필요 / 비정형 데이터 / 거대 쓰기 처리량 / 단순 key-value 패턴.

## 전형적 사용 사례

- 트랜잭션이 중요한 OLTP(결제·주문·계정·재무).
- 복잡한 질의·리포팅·집계.
- 다대다 관계가 많은 도메인(사용자·역할·권한).
- 1장의 web/data tier 분리 직후 등장하는 기본 데이터 저장소.

## 실무 함정

- **ALTER TABLE의 락 비용**: 대용량 테이블 스키마 변경은 락·다운타임. **온라인 DDL 도구** 필수 (pt-online-schema-change, gh-ost, PostgreSQL 12+의 concurrent index 등).
- **Connection pool 고갈**: max_connections 한도가 RDBMS의 단단한 상한. PgBouncer, ProxySQL 같은 connection pooler를 앞단에.
- **N+1 query**: ORM의 lazy loading 함정. eager loading·batch loading·DataLoader 패턴으로 해결.
- **Over-indexing**: 모든 컬럼에 index = write 폭주 시 비용 폭증·디스크 폭증. 슬로우 쿼리 로그·EXPLAIN으로 실제 사용되는 index만 유지.
- **Long-running transaction**: lock 시간 길어지면 다른 트랜잭션 대기. autovacuum 방해(PostgreSQL)·bloat 누적.
- **백업 검증 안 함**: 백업 실행만으로는 부족. 정기적 **복구 훈련**이 진짜 안전망. RPO/RTO 측정.
- **읽기 복제본 의존 후의 lag**: read replica로 쓰는 화면이 갑자기 stale 보임. 중요 read는 master로, 부수적인 건 replica로 명시적 라우팅.
- **Vendor lock-in**: RDBMS 종류 간 SQL 방언·proprietary 함수 차이 큼. 이식성을 원하면 ANSI 표준 위주.

## 등장 사례

- ch01 — 단일 서버에서 분리되는 시점에 기본 DB로 가정. [[database-replication]]과 [[sharding]]의 주 대상.
