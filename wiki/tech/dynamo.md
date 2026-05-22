---
type: tech
category: db
sources: [ch05, ch06]
---

# Amazon Dynamo

## 한 줄 정의

Amazon이 2007년 발표한 **분산 key-value store**. AP·eventual consistency·decentralized 아키텍처의 표준 모범으로, 본 위키 ch05·ch06이 다룬 거의 모든 분산 기법의 **원조 출처**다 (Dynamo paper, SOSP 2007) (ch05 [3], ch06 [4]).

> ⚠️ 본 페이지의 "Dynamo"는 Amazon 내부 system을 가리키는 **논문 속 시스템**이다. 현재 AWS가 제공하는 매니지드 서비스 **DynamoDB**는 Dynamo paper의 아이디어를 차용했지만 별개 제품 — 본 페이지 후반에서 구분.

## 주요 특성

- **AP 시스템**: [[cap-theorem|네트워크 파티션 시 가용성 우선]], stale 데이터 허용.
- **Always writable**: 쓰기는 절대 거부하지 않는다는 설계 원칙 (쇼핑카트 도메인 요구).
- **Decentralized**: 모든 노드 동등. coordinator는 역할이지 노드 종류가 아님.
- **Eventual consistency**: 충돌은 클라이언트가 reconcile.
- **Tunable**: N/W/R로 일관성·지연·가용성 조정.

## 핵심 기법 (위키 페이지 매핑)

| 영역 | Dynamo 채택 기법 |
|---|---|
| 데이터 분배 | [[consistent-hashing]] + virtual nodes |
| 복제 | clockwise N 노드, cross-DC 옵션 |
| 일관성 | [[quorum-consensus]] N/W/R |
| 충돌 해결 | [[vector-clock]] + 클라이언트 머지 |
| 멤버십·장애 탐지 | [[gossip-protocol]] |
| 임시 장애 | [[sloppy-quorum-hinted-handoff]] |
| 영구 장애·anti-entropy | [[merkle-tree]] |
| 일관성 모델 | [[consistency-models|eventual consistency]] |

ch06이 그대로 Dynamo paper 5절의 구조를 따라간다.

## 언제 선택하는가 / 대안 비교

본 페이지는 Dynamo paper 자체를 다룬다 — 실제로 "Dynamo를 선택"하는 사람은 없다 (내부 시스템). 비교 대상은 그 영향을 받은 시스템들:

| 후보 | 특징 | 출처 |
|---|---|---|
| **DynamoDB (AWS)** | Dynamo + BigTable 융합, 매니지드 | Amazon 상용 서비스 |
| **Cassandra** | Dynamo + BigTable storage engine | Facebook origin, ASF |
| **Riak** | Dynamo의 가장 충실한 오픈소스 클론 | Basho (deprecated 2017) |
| **Voldemort** | LinkedIn의 Dynamo 클론 | 사실상 deprecated |
| **ScyllaDB** | Cassandra 호환, C++ 재구현 | 성능 우선 |

## 전형적 사용 사례

Dynamo paper의 Amazon 내부 사용 사례 (paper 1절):

- **Shopping cart**: 가용성 최우선, 충돌은 union으로 머지 — Dynamo의 대표 use case.
- **Best seller list**: read-heavy.
- **Customer preferences**: 사용자별 잘 안 바뀌는 데이터.
- **Session management**: 임시 KV.
- **Product catalog**: 변경 빈도 낮음.

핵심 공통점: **"잃기보단 일시 stale이 낫다"** 도메인.

## 실무 함정

> Dynamo 자체는 직접 운영 안 하므로 실무 함정은 Dynamo 영감 시스템들([[cassandra]]·DynamoDB 등) 페이지에서 다룬다. 본 페이지는 paper로서의 함정.

- **클라이언트 충돌 머지의 도메인 복잡도**: 카트 union은 쉽지만 모든 도메인에 그런 자연스러운 머지 함수가 있지 않음.
- **Vector clock truncation**: 노드 수 많아지면 vector 크기 폭증 → 오래된 entry 제거. ancestor 판정 오류 가능성.
- **"Always writable" 도메인 가정**: 일부 도메인(잔액)에는 부적합. Dynamo가 모든 KV에 정답은 아님.

## DynamoDB와의 차이 (혼동 방지)

| 항목 | Dynamo (paper) | DynamoDB (AWS 서비스) |
|---|---|---|
| 출시 | 2007 paper | 2012 매니지드 서비스 |
| 합의 모델 | leaderless + quorum | 파티션별 leader (Paxos 기반으로 알려짐) |
| 충돌 해결 | vector clock + 클라이언트 머지 | last-write-wins (timestamp) |
| 일관성 | eventual default | eventual default, strong 옵션 |
| 인터페이스 | 단순 KV | KV + secondary index + query API |
| Storage engine | unspecified (paper) | LSM 추정 |
| 운영 | 사용자 자체 운영 | 완전 매니지드 |

→ **"DynamoDB"는 Dynamo paper + BigTable storage + AWS 운영 노하우의 융합**. paper의 모든 기법이 그대로 들어 있지는 않다.

## 등장 사례

- ch05 — [[consistent-hashing]] 채택 시스템 사례.
- ch06 — KV store 설계의 모든 컴포넌트 출처. paper [4]로 직접 인용.
- **AWS DynamoDB** — 상용 후계.
- **Cassandra·Riak·Voldemort** — Dynamo 영감 시스템들.
- 학계·산업의 **Eventually consistent KV** 패턴의 출발점.

## 참고 문헌

- Giuseppe DeCandia et al., "Dynamo: Amazon's Highly Available Key-value Store", SOSP 2007.
  https://www.allthingsdistributed.com/files/amazon-dynamo-sosp2007.pdf
- Werner Vogels, "Eventually Consistent", ACM Queue 2008.
