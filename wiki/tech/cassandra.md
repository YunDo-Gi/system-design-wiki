---
type: tech
category: db
sources: [ch05, ch06]
---

# Apache Cassandra

## 한 줄 정의

Facebook이 2008년 공개·이후 Apache Foundation 이관한 **분산 wide-column store**. [[dynamo|Dynamo]]의 partitioning·replication·anti-entropy 기법과 **BigTable의 LSM storage engine**을 융합한 AP·tunable consistency 시스템 (Lakshman & Malik, 2009) (ch05 [4], ch06 [5][8]).

## 주요 특성

- **AP 시스템** (W/R 튜닝으로 strong 가능): [[cap-theorem]] AP 계열 표준.
- **Decentralized**: 모든 노드 동등, leader 없음.
- **Tunable consistency**: per-query `ONE / QUORUM / LOCAL_QUORUM / EACH_QUORUM / ALL`.
- **LSM storage engine**: memtable + commit log + SSTable + compaction.
- **Wide-column model**: KV보다 풍부 — partition key + clustering key + columns.
- **Linear scalability**: 노드 추가가 거의 선형으로 처리량 증가.

## 핵심 컴포넌트 (위키 페이지 매핑)

| 영역 | Cassandra 채택 |
|---|---|
| 데이터 분배 | [[consistent-hashing]] (Murmur3 partitioner) + virtual nodes (vnodes=256 default) |
| 복제 | clockwise N nodes + rack/DC-aware `NetworkTopologyStrategy` |
| 일관성 | [[quorum-consensus]] per-query consistency level |
| 충돌 해결 | **LWW (timestamp)** — Dynamo와 달리 vector clock 채택 안 함 |
| 멤버십 탐지 | [[gossip-protocol]] + Phi Accrual failure detector |
| 임시 장애 | [[sloppy-quorum-hinted-handoff]] (system.hints 테이블) |
| 영구 장애 | [[merkle-tree]] anti-entropy (`nodetool repair`) |
| Storage | [[lsm-tree-storage-engine]] + [[bloom-filter]] (SSTable별) |
| Multi-DC | cross-DC replication, `LOCAL_QUORUM`/`EACH_QUORUM` |

ch06 write/read path가 Cassandra 모델 그대로다 (paper [8]).

## 언제 선택하는가 / 대안 비교

| 후보 | 강점 | 약점 |
|---|---|---|
| **Cassandra** | linear scale, multi-DC, write-heavy | 복잡한 운영, JVM 튜닝 |
| **ScyllaDB** | Cassandra 호환 + C++ 재구현, ~10배 처리량 | 생태계 더 작음 |
| **DynamoDB** | 매니지드, secondary index, ACID | AWS 종속, 비용 |
| **HBase** | Hadoop 생태계, strong consistency | CP·운영 복잡 |
| **MongoDB** | document model, secondary index 풍부 | scale-out 약함, CP 가까움 |
| **CockroachDB** | strong consistency + SQL | latency·throughput Cassandra 대비 약함 |

**Cassandra가 적합한 경우**:
- write-heavy + time-series + 수십~수백 노드 클러스터.
- multi-DC 글로벌 복제.
- tunable consistency가 도메인적으로 필요.

**부적합한 경우**:
- 강한 트랜잭션·복잡한 join이 필요한 OLTP.
- 작은 규모 (운영 오버헤드가 이득보다 큼).
- 빈번한 update·delete 워크로드 (tombstone 누적).

## 전형적 사용 사례

- **시계열 데이터**: 메트릭·IoT·로그 — write-heavy + time-based clustering key.
- **메시징 inbox**: Discord 등 (수십억 메시지).
- **추천·feed**: Netflix (대표 채택 기업).
- **session·preference store**: 글로벌 규모.

## 실무 함정

- **Tombstone 누적**: 빈번한 delete는 tombstone 폭발 → read latency↑. TTL·compaction 튜닝 필수.
- **Wide row 함정**: 한 partition key에 너무 많은 row → hotspot + GC 압박. 보통 100MB/partition 한도.
- **Compaction 폭주**: write 폭주 시 compaction이 따라가지 못해 SSTable 누적. throughput·전략(size-tiered vs leveled) 조정.
- **`nodetool repair`의 비용**: 클러스터 전체 anti-entropy는 며칠 걸릴 수 있음. 정기 일정·incremental repair.
- **Consistency level 혼동**: `ONE`만 쓰다가 multi-DC 망가짐. `LOCAL_QUORUM` 디폴트 권장.
- **Vector clock 없음 = LWW**: 동시 쓰기 시 timestamp 순서대로 덮어씀 — 잃는 쓰기 발생. 클럭 skew 주의.
- **JVM tuning**: GC pause가 latency 폭증의 주범. G1GC/ZGC 튜닝 필요.
- **schema evolution**: ALTER TABLE은 가능하지만 데이터 모델 재설계는 어려움.
- **secondary index 한계**: cardinality 낮은 컬럼만 효과적. 잘못 쓰면 cluster-wide scan.

## 모니터링 핵심 지표

| 지표 | 의미 |
|---|---|
| read/write latency (p50/p99/p999) | 일반 SLO |
| pending compactions | 누적되면 read latency↑ |
| dropped mutations | overload 징후 |
| tombstone scan count | delete-heavy 워크로드 경고 |
| hints in flight | 노드 장애 누적 |
| GC pause time | JVM 튜닝 필요 신호 |

## 등장 사례

- ch05 — [[consistent-hashing]] 채택 시스템.
- ch06 — write/read path 직접 모델, 거의 모든 분산 기법 사례.
- **Apple** — 10만+ 노드, 수십 PB.
- **Netflix** — global session·메타데이터.
- **Discord** — 메시지 백엔드 (수십억 메시지/일), 이후 ScyllaDB 부분 이전.
- **Instagram** — early scaling.
- **eBay·Walmart·Reddit** — 부분 채택.

## 참고 문헌

- Lakshman & Malik, "Cassandra - A Decentralized Structured Storage System", LADIS 2009.
  http://www.cs.cornell.edu/Projects/ladis2009/papers/Lakshman-ladis2009.PDF
- Cassandra docs: https://cassandra.apache.org/doc/latest/architecture/
