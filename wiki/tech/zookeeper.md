---
type: tech
category: observability
sources: [ch12]
---

# Apache ZooKeeper

## 한 줄 정의

분산 시스템의 **코디네이션(coordination)**을 담당하는 오픈소스 서비스 — 설정 관리, 네이밍, 리더 선출, 그룹 멤버십, **service discovery**를 일관성 있게 제공한다. 작은 데이터를 강한 일관성으로 저장하는 계층적 키 저장소(znode)다 (ch12, p.189).

## 주요 특성

- **강한 일관성**: ZAB(Zookeeper Atomic Broadcast) 합의로 모든 노드가 같은 순서로 갱신을 본다.
- **znode 트리**: 파일시스템 유사 계층 구조. ephemeral znode는 세션이 끊기면 자동 삭제 → 헬스체크·presence에 유용.
- **watch**: 노드 변경을 구독해 알림 받음 → 동적 멤버십 감지.
- 소량·고빈도 읽기 메타데이터에 최적(대용량 데이터 저장소가 아님).

## 언제 선택하는가 / 대안 비교

| 후보 | 합의 | 용도 | 비고 |
|---|---|---|---|
| **ZooKeeper** | ZAB | 코디네이션·리더선출·discovery | 성숙, Kafka/HBase가 사용 |
| etcd | Raft | k8s 백엔드·설정·discovery | 더 단순한 API, gRPC |
| Consul | Raft | service discovery·헬스체크 | DNS 인터페이스 내장 |

핵심 판단: 코디네이션은 **직접 구현하지 말 것**(분산 합의는 버그의 온상). 검증된 서비스를 쓴다. 생태계가 Kafka/HBase면 ZooKeeper, 쿠버네티스/클라우드 네이티브면 etcd·Consul이 자연스럽다.

## 전형적 사용 사례

- [[service-discovery]]: 가용 서버 등록 + 최적 인스턴스 선택 (ch12 chat server 배정).
- 리더 선출: 마스터 1개를 합의로 선출 (HBase region server 등).
- 분산 락·배리어, 설정 공유.

## 실무 함정

- **대용량 데이터 저장 금지** — znode는 KB 단위 메타데이터용. 메시지·콘텐츠를 넣으면 안 됨.
- 자체가 SPOF가 되지 않게 홀수 노드(3·5) 앙상블로 운영, 과반 합의 필요.
- watch는 one-shot(한 번 발화 후 재등록 필요) — 놓침 방지 로직 필요.
- ZooKeeper 장애가 의존 시스템 전체를 멈출 수 있어 의존성 최소화 추세(Kafka는 KRaft로 ZooKeeper 제거 중).

## 등장 사례

- ch12 — chat server service discovery 코디네이션
- Kafka(구버전)·HBase — 클러스터 메타데이터·리더 선출
- [[cassandra]]는 ZooKeeper 비사용(gossip 기반 decentralized) — 대조 사례
