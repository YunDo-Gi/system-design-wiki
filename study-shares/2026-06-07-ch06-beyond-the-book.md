# 분산 KV, 책 이후의 이야기

ch06은 2007년 Amazon Dynamo 논문을 학습용으로 풀어쓴 장이다. 그래서 책의 결론은 "2007년 기준의 정답"이고, 그 뒤로 현실은 꽤 다른 길을 갔다. 챕터를 이미 읽었다면 책 요약보다 이 간극을 보는 편이 낫겠다 싶어 정리했다.

세 가지를 다룬다. 책이 충돌 해결의 표준으로 제시한 vector clock이 현실에서 거의 쓰이지 않게 된 이유, CAP만으로는 부족해서 나온 PACELC, 그리고 Dynamo 논문의 설계가 정작 Amazon의 상용 서비스에서 어떻게 바뀌었는지다.

## vector clock은 왜 현실에서 밀려났나

책에서는 복제본이 갈라졌을 때 vector clock으로 선후관계와 충돌(sibling)을 판정하고, 충돌이면 두 버전을 클라이언트에 돌려줘서 합치게 한다(장바구니 union이 대표 예). 논리적으로는 깔끔한데, 막상 이걸 채택한 시스템은 많지 않다.

Cassandra는 처음부터 vector clock을 쓰지 않았다. 대신 모든 변경에 timestamp를 찍고 가장 최근 것이 이기는 LWW(Last-Write-Wins) 방식을 택했다. 초기에 성능을 이유로 vector clock을 구현하지 않았고, 대신 하나의 row를 column 단위로 쪼개 각각 독립적으로 머지하는 방식으로 충돌 자체를 줄였다. vector clock이 풀려던 문제를 데이터 모델로 우회한 셈이다. 다만 LWW는 동시에 일어난 두 쓰기 중 하나를 그냥 버리기 때문에, "정보를 비결정적으로 파괴하는 별로 좋지 않은 CRDT"라는 비판을 받는다([DataStax](https://www.datastax.com/blog/why-cassandra-doesnt-need-vector-clocks), [aphyr](https://aphyr.com/posts/299-the-trouble-with-timestamps)).

Riak은 vector clock을 그대로 노출했던 시스템인데, 결국 CRDT로 무게중심을 옮겼다. sibling 충돌을 개발자가 직접 머지 함수를 짜서 해결해야 하는 부담이 너무 컸기 때문이다. Riak 2.0에서 도입한 Data Types(CRDT)는 "개발자가 다시는 머지 함수를 짤 필요가 없게" 그 책임을 애플리케이션에서 데이터베이스로 흡수하는 것이 목표였다([Riak 2.0](https://riak.com/distributed-data-types-riak-2-0/), [CRDT 역사 정리](https://christophermeiklejohn.com/erlang/lasp/2019/03/08/monotonicity.html)).

그래서 지금은 CRDT(Conflict-free Replicated Data Type)가 vector clock의 자리를 상당 부분 대신한다. 충돌을 감지해서 클라이언트에게 떠넘기는 대신, 자료구조 자체에 "어떻게 합쳐지는가"를 정의해두는 발상이다. 예를 들어 장바구니를 OR-Set으로 만들면 vector clock 없이도 두 복제본이 자동으로 합집합으로 수렴한다. 협업 편집(Figma, Notion)이나 Redis CRDT, Automerge 같은 것들이 이 계열이다.

정리하면, vector clock은 이론적으로 옳지만 충돌 해결 부담을 클라이언트에 떠넘긴다는 점이 운영에서 무거웠고, 그 부담을 데이터 모델(Cassandra)이나 자료구조(CRDT)로 옮기는 쪽으로 흐름이 바뀌었다.

## CAP만으로는 부족하다 — PACELC

책은 네트워크 파티션이 불가피하니 결국 CP냐 AP냐의 선택이라고 정리한다. 맞는 말이지만, CAP은 파티션이 일어났을 때의 행동만 설명한다. 복제가 있는 시스템은 파티션이 없는 평상시에도 트레이드오프가 있다. 쓰기를 모든 복제본이 받을 때까지 기다리면 일관성은 높아지지만 느려지고, 일부만 기다리고 응답하면 빨라지지만 잠깐 옛날 값을 읽을 수 있다.

PACELC는 이걸 한 줄로 정리한다. 파티션(P)이면 가용성(A)과 일관성(C) 사이에서, 그렇지 않은 평소(E, else)면 지연(L)과 일관성(C) 사이에서 고른다는 것이다. Daniel Abadi가 2010년 블로그에서 제안하고 2012년 논문으로 정리했다([논문](https://www.researchgate.net/publication/220476540_Consistency_Tradeoffs_in_Modern_Distributed_Database_System_Design_CAP_is_Only_Part_of_the_Story), [Wikipedia](https://en.wikipedia.org/wiki/PACELC_design_principle)).

이 틀로 보면 시스템 성격이 더 또렷해진다. DynamoDB나 Cassandra는 파티션 시 가용성을 택하고 평소엔 저지연을 택하는 PA/EL이고, Google Spanner나 CockroachDB는 양쪽 모두 일관성을 우선하는 PC/EC다. 실제 운영의 대부분은 파티션이 없는 평소 상태이므로, "이 DB가 평소에 지연과 일관성 중 뭘 택했나"를 보는 PACELC가 CAP보다 실용적인 경우가 많다.

## Dynamo 논문과 DynamoDB는 다른 시스템이다

책이 다루는 Dynamo는 2007년 논문 속의 내부 시스템이고, 흔히 같은 것으로 오해하는 AWS DynamoDB(2012)는 별개다. 그냥 이름만 비슷한 게 아니라 아키텍처가 상당히 다르다.

2022년 USENIX ATC에 AWS 엔지니어들이 직접 쓴 DynamoDB 논문은 "DynamoDB의 아키텍처는 2007년 Dynamo와 공유하는 부분이 별로 없다"고 명시한다. 가장 큰 차이는 복제 방식이다. 논문 속 Dynamo는 리더가 없는(leaderless) quorum 기반이지만, DynamoDB는 파티션마다 리더를 두고 MultiPaxos로 복제한다. 충돌 해결도 vector clock 대신 LWW를 쓴다. 우아한 leaderless 모델이 10년의 매니지드 운영을 거치면서, 예측 가능한 성능과 강한 일관성 옵션을 위해 리더 기반으로 바뀐 것이다(참고로 2021년 Prime Day에 초당 8,920만 요청을 처리했다)([USENIX ATC 2022 논문](https://www.usenix.org/system/files/atc22-elhemali.pdf), [Marc Brooker 정리](https://brooker.co.za/blog/2022/07/12/dynamodb.html)).

## 덧붙여: sloppy quorum의 함정

W+R>N이면 강한 일관성이라는 설명은 strict quorum일 때만 맞다. 노드가 죽었을 때 살아있는 다른 노드로 정족수를 채우는 sloppy quorum에서는 읽기 집합과 쓰기 집합이 겹치지 않을 수 있어서, W+R>N이어도 옛날 값을 읽을 수 있다. Martin Kleppmann은 이를 두고 "엄밀히는 quorum이 아니다"라고 표현한다(*Designing Data-Intensive Applications* 5장, [정리](https://timilearning.com/posts/ddia/part-two/chapter-5/)).

## 이야기 나눠볼 만한 것들

- 이론적으로 옳은 vector clock이 운영에서 밀린 걸 보면, 충돌 해결의 복잡도를 어디에 둘지(클라이언트 / 데이터베이스 / 자료구조)가 결국 채택을 가른 것 같다. 우리라면 어디에 두겠는가.
- 우리 회사 데이터(MySQL, Elasticsearch)를 PACELC로 분류하면 각각 뭘까. 결제와 검색은 같은 선택일까.
- Amazon이 leaderless를 두고 Paxos로 돌아간 건, 대규모 운영에서는 우아함보다 예측 가능성이 중요하다는 신호로 읽어도 될까.

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
