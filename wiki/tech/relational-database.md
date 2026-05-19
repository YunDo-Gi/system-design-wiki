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
- 한계: 쓰기·저장 용량 수평 확장이 어렵다 → [[database-replication]]으로 읽기 분산, [[sharding]]으로 쓰기 분산. 샤딩 후엔 cross-shard join이 어려워 [[stateless-web-tier|de-normalization]]이 흔한 우회책.

## 전형적 사용 사례

- 트랜잭션이 중요한 OLTP(결제·주문·계정).
- 복잡한 질의·리포팅이 필요한 도메인.
- 1장의 web/data tier 분리 직후 등장하는 기본 데이터 저장소.

## 등장 사례

- ch01 — 단일 서버에서 분리되는 시점에 기본 DB로 가정. [[database-replication]]과 [[sharding]]의 주 대상.
