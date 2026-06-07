# 분산 KV, 책 이후의 이야기

ch06(Dynamo 논문)의 결론 중 그 뒤로 현실이 다르게 간 지점들.

## vector clock은 현실에서 거의 안 쓴다

책은 복제본이 갈라지면 vector clock으로 충돌을 판정하고, 충돌이면 두 버전을 클라이언트가 합치게 한다(장바구니 union). 논리는 깔끔한데 채택은 드물다.

- **Cassandra**: 처음부터 안 씀. 변경마다 timestamp 찍고 최신값이 이기는 LWW. row를 column 단위로 쪼개 독립 머지해서 충돌 자체를 줄임. 단 LWW는 동시 쓰기 중 하나를 그냥 버린다("정보를 비결정적으로 파괴하는 별로 안 좋은 CRDT"). [DataStax](https://www.datastax.com/blog/why-cassandra-doesnt-need-vector-clocks), [aphyr](https://aphyr.com/posts/299-the-trouble-with-timestamps)
- **Riak**: vector clock을 노출했다가 CRDT로 이동. sibling 머지 함수를 개발자가 직접 짜는 부담이 컸다. Riak 2.0의 Data Types가 그 책임을 앱에서 DB로 흡수. [Riak 2.0](https://riak.com/distributed-data-types-riak-2-0/), [CRDT 역사](https://christophermeiklejohn.com/erlang/lasp/2019/03/08/monotonicity.html)
- **CRDT가 후계**: 충돌을 클라이언트에 떠넘기는 대신, 자료구조 자체에 "어떻게 합쳐지는지"를 정의. 장바구니를 OR-Set으로 만들면 자동으로 합집합 수렴. Figma·Notion 협업 편집, Redis CRDT, Automerge가 이 계열.

핵심: vector clock은 충돌 해결 부담을 클라이언트에 둔 게 무거웠고, 그 부담을 데이터 모델(Cassandra)이나 자료구조(CRDT)로 옮기는 쪽으로 흐름이 바뀌었다.

## CAP → PACELC

CAP은 파티션이 났을 때만 설명한다. 파티션이 없는 평소에도 트레이드오프가 있다: 모든 복제본을 기다리면 일관성↑·느림, 일부만 기다리면 빠름·stale 가능.

- **PACELC**: 파티션(P)이면 A vs C, 평소(E)면 L(지연) vs C(일관성). Daniel Abadi 2010 블로그 → 2012 논문. [논문](https://www.researchgate.net/publication/220476540_Consistency_Tradeoffs_in_Modern_Distributed_Database_System_Design_CAP_is_Only_Part_of_the_Story), [Wikipedia](https://en.wikipedia.org/wiki/PACELC_design_principle)
- **PA/EL**: DynamoDB, Cassandra (파티션 시 가용성, 평소 저지연)
- **PC/EC**: Spanner, CockroachDB (항상 일관성)

운영의 대부분은 파티션 없는 평소이므로, "평소에 지연과 일관성 중 뭘 택했나"를 보는 PACELC가 더 실용적일 때가 많다.

## Dynamo 논문 ≠ DynamoDB

책의 Dynamo는 2007년 논문 속 내부 시스템, AWS DynamoDB(2012)는 별개 제품이고 아키텍처도 다르다.

- 2022 USENIX ATC 논문(AWS 엔지니어 작성)이 직접 명시: "DynamoDB는 2007 Dynamo와 공유하는 부분이 별로 없다."
- 복제: Dynamo는 leaderless quorum, DynamoDB는 파티션마다 리더 + MultiPaxos.
- 충돌 해결: vector clock 대신 LWW.
- 규모 참고: 2021 Prime Day 초당 8,920만 요청.
- [USENIX ATC 2022](https://www.usenix.org/system/files/atc22-elhemali.pdf), [Marc Brooker](https://brooker.co.za/blog/2022/07/12/dynamodb.html)

## sloppy quorum의 함정

W+R>N이 강한 일관성을 주는 건 strict quorum일 때만. 죽은 노드 대신 다른 노드로 정족수를 채우는 sloppy quorum에서는 읽기·쓰기 집합이 안 겹칠 수 있어 stale read 가능. Kleppmann은 "엄밀히는 quorum이 아니다"라고 표현(*Designing Data-Intensive Applications* 5장). [정리](https://timilearning.com/posts/ddia/part-two/chapter-5/)

## 이야기 나눠볼 것

- 충돌 해결 복잡도를 어디에 둘까 — 클라이언트 / DB / 자료구조.
- 우리 데이터(MySQL, ES)를 PACELC로 분류하면? 결제와 검색은 같은 선택일까.
- Amazon이 leaderless → Paxos로 간 건 "규모에선 우아함보다 예측 가능성"의 신호일까.

## 출처

- [Why Cassandra Doesn't Need Vector Clocks — DataStax](https://www.datastax.com/blog/why-cassandra-doesnt-need-vector-clocks)
- [Dynamo — Apache Cassandra 공식 문서](https://cassandra.apache.org/doc/latest/cassandra/architecture/dynamo.html)
- [The trouble with timestamps — Kyle Kingsbury](https://aphyr.com/posts/299-the-trouble-with-timestamps)
- [Distributed Data Types – Riak 2.0](https://riak.com/distributed-data-types-riak-2-0/)
- [A Brief History of CRDTs in Riak — Christopher Meiklejohn](https://christophermeiklejohn.com/erlang/lasp/2019/03/08/monotonicity.html)
- [PACELC 논문(2012) — Daniel Abadi](https://www.researchgate.net/publication/220476540_Consistency_Tradeoffs_in_Modern_Distributed_Database_System_Design_CAP_is_Only_Part_of_the_Story)
- [PACELC — Wikipedia](https://en.wikipedia.org/wiki/PACELC_design_principle)
- [Amazon DynamoDB (USENIX ATC 2022)](https://www.usenix.org/system/files/atc22-elhemali.pdf)
- [The DynamoDB paper — Marc Brooker](https://brooker.co.za/blog/2022/07/12/dynamodb.html)
- Martin Kleppmann, *Designing Data-Intensive Applications*, 5장 Replication
- Giuseppe DeCandia et al., *Dynamo: Amazon's Highly Available Key-value Store*, SOSP 2007
