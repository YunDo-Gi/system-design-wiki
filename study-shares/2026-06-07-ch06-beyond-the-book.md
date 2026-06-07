# 분산 KV, 책 이후의 이야기

ch06(Dynamo 논문)의 결론 중 그 뒤로 현실이 다르게 간 지점들.

## vector clock과 그 이후

vector clock은 각 값에 `[서버, 카운터]` 배열을 붙여, 두 버전이 선후 관계인지 동시에 갈라진 충돌인지 판정하는 방법이다. 충돌이면 시스템이 두 버전을 모두 클라이언트에 돌려주고, 클라이언트가 도메인 지식으로 합친다. Dynamo 논문이 충돌 해결의 표준으로 제시했다.

이후 실제 시스템들의 선택:

- **Cassandra — LWW(Last-Write-Wins)**: vector clock 대신 변경마다 timestamp를 찍고 최신값이 이긴다. row를 column 단위로 쪼개 각각 독립적으로 머지해 충돌 자체를 줄인다. 동시 쓰기 중 하나는 버려지므로 "정보를 비결정적으로 파괴한다"는 비판이 있다. [DataStax](https://www.datastax.com/blog/why-cassandra-doesnt-need-vector-clocks), [aphyr](https://aphyr.com/posts/299-the-trouble-with-timestamps)
- **Riak — CRDT로 이동**: vector clock을 노출했으나, 충돌 머지 로직을 개발자가 직접 짜는 부담 때문에 Riak 2.0에서 CRDT(Data Types)로 옮겼다. [Riak 2.0](https://riak.com/distributed-data-types-riak-2-0/), [CRDT 역사](https://christophermeiklejohn.com/erlang/lasp/2019/03/08/monotonicity.html)
- **CRDT(Conflict-free Replicated Data Type)**: 충돌을 클라이언트에 넘기는 대신, 자료구조 자체에 머지 규칙을 정의해 복제본이 자동으로 같은 값으로 수렴하게 한다. 예) 집합을 OR-Set으로 만들면 두 복제본이 합집합으로 합쳐진다. 협업 편집(Figma·Notion), Redis CRDT, Automerge가 이 방식.

흐름을 한 줄로: 충돌 해결의 복잡도를 클라이언트에서 데이터 모델(Cassandra)이나 자료구조(CRDT) 쪽으로 옮겨 왔다.

## CAP에서 PACELC로

CAP은 네트워크 파티션이 났을 때 일관성(C)과 가용성(A) 중 하나를 고른다는 정리다. 한계는 파티션이 났을 때만 설명한다는 것. 복제가 있으면 파티션이 없는 평소에도 트레이드오프가 있다 — 모든 복제본의 응답을 기다리면 일관성은 오르지만 느려지고, 일부만 기다리면 빨라지지만 옛날 값을 읽을 수 있다.

PACELC는 여기에 한 축을 더한다: 파티션(P)이면 A vs C, 평소(E)면 지연(L) vs 일관성(C). Daniel Abadi가 2010년 블로그, 2012년 논문으로 정리했다. [논문](https://www.researchgate.net/publication/220476540_Consistency_Tradeoffs_in_Modern_Distributed_Database_System_Design_CAP_is_Only_Part_of_the_Story), [Wikipedia](https://en.wikipedia.org/wiki/PACELC_design_principle)

- **PA/EL**: DynamoDB, Cassandra — 파티션 시 가용성, 평소 저지연
- **PC/EC**: Spanner, CockroachDB — 항상 일관성 우선

운영의 대부분은 파티션이 없는 평소 상태라, "평소에 지연과 일관성 중 무엇을 택했나"를 함께 보는 PACELC가 시스템 성격을 더 정확히 분류한다.

## Dynamo 논문 ≠ DynamoDB

책의 Dynamo는 2007년 논문 속 Amazon 내부 시스템이고, AWS DynamoDB(2012)는 이름만 이어받은 별개 제품이다. 아키텍처가 다르다.

- 2022 USENIX ATC 논문(AWS 엔지니어 작성)이 직접 명시: "DynamoDB는 2007 Dynamo와 공유하는 부분이 별로 없다."
- 복제: Dynamo는 리더 없는 quorum, DynamoDB는 파티션마다 리더를 두고 MultiPaxos.
- 충돌 해결: vector clock 대신 LWW.
- 규모 참고: 2021 Prime Day에 초당 8,920만 요청.
- [USENIX ATC 2022](https://www.usenix.org/system/files/atc22-elhemali.pdf), [Marc Brooker](https://brooker.co.za/blog/2022/07/12/dynamodb.html)

## 이야기 나눠볼 것

- 충돌 해결 복잡도를 어디에 둘까 — 클라이언트 / DB / 자료구조.
- 우리 데이터(MySQL, ES)를 PACELC로 분류하면? 결제와 검색은 같은 선택일까.
- Amazon이 리더 없는 구조에서 Paxos로 간 건 "규모에선 단순함보다 예측 가능성"의 신호일까.

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
- Giuseppe DeCandia et al., *Dynamo: Amazon's Highly Available Key-value Store*, SOSP 2007
