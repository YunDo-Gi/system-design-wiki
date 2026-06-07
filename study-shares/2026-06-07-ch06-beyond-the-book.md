# 분산 KV, 책 이후의 이야기

ch06(Dynamo 논문)의 결론 중 그 뒤로 현실이 다르게 간 지점들.

## vector clock과 그 이후

vector clock은 각 값에 `[서버, 카운터]` 배열을 붙여, 두 버전이 선후 관계인지 동시에 갈라진 충돌인지 판정하는 방법이다. 충돌이면 시스템이 두 버전을 모두 클라이언트에 돌려주고, 클라이언트가 도메인 지식으로 합친다. Dynamo 논문이 충돌 해결의 표준으로 제시했다.

vector clock 대신 실제 시스템이 택한 두 가지 방식이 LWW와 CRDT다.

**LWW (Last-Write-Wins)**

모든 변경에 timestamp를 찍고, 충돌이 나면 그냥 timestamp가 가장 늦은 값을 최종값으로 삼는다. 버전 족보를 추적할 필요 없이 숫자 비교 한 번으로 끝나 단순하고 빠르다. 대가는, 동시에 일어난 두 변경 중 진 쪽이 흔적 없이 사라진다는 것이다(lost write). 그래서 "정보를 비결정적으로 파괴한다"는 비판을 받는다.

Cassandra가 이 방식이다. 처음부터 vector clock을 안 쓰고 LWW를 택했고, 대신 row를 column 단위로 쪼개 각 column을 독립적으로 LWW 처리해서 한 값 전체가 통째로 덮이는 걸 줄였다. [DataStax](https://www.datastax.com/blog/why-cassandra-doesnt-need-vector-clocks), [aphyr](https://aphyr.com/posts/299-the-trouble-with-timestamps)

**CRDT (Conflict-free Replicated Data Type)**

충돌을 감지해서 누군가 풀게 하는 게 아니라, 자료구조 자체에 "어떻게 합쳐지는가"를 미리 정의해둔 것. 머지 연산을 교환·결합·멱등하게 설계하면, 복제본들이 변경을 **어떤 순서로 받아도 결국 같은 값으로 수렴**한다. 그래서 클라이언트가 머지 로직을 짤 필요가 없다. 카운터(G-Counter), 집합(OR-Set: 두 복제본을 합집합으로 합침), 텍스트 등 타입별로 정의돼 있다. 협업 편집(Figma·Notion), Redis CRDT, Automerge가 이 방식.

Riak이 이 길로 갔다. 원래 vector clock을 노출했는데 충돌 머지를 개발자가 직접 짜는 부담이 커서, Riak 2.0에서 CRDT(Data Types)로 그 책임을 DB 안으로 흡수했다. [Riak 2.0](https://riak.com/distributed-data-types-riak-2-0/), [CRDT 역사](https://christophermeiklejohn.com/erlang/lasp/2019/03/08/monotonicity.html)

세 방식을 비교하면, vector clock은 충돌 해결을 클라이언트에 맡기고, LWW는 timestamp로 한쪽을 버려 자동 처리하고, CRDT는 자료구조가 잃지 않고 합치도록 한다.

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
