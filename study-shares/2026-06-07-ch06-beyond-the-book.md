# ch06 그 이후 — 책이 안 알려준 분산 KV의 후일담

> 스터디 공유용. 대상: *System Design Interview* ch06(Design a Key-Value Store)을 **이미 읽고 온** 사람들.
> 목적: 책 요약을 반복하지 않고, **책이 정답처럼 제시한 것이 현실에서 어떻게 뒤집혔는지**를 출처와 함께 본다.
> 작성: 2026-06-07

---

## 0. 왜 이 발표인가

ch06은 사실상 **2007년 Amazon Dynamo 논문**을 학습용으로 재구성한 장이다. 그래서 책의 결론들은 "2007년의 정답"이고, 그 뒤 약 15년간 현실은 상당 부분 **다른 길**로 갔다. 챕터를 뗀 사람에게 가치 있는 건 그 간극이다.

이 발표의 한 문장:

> **"책이 충돌 해결의 정답이라 한 vector clock을, 정작 Cassandra·Riak·DynamoDB는 안 쓴다. 왜 그런지가 책보다 더 중요한 교훈이다."**

---

## 1. 책의 주장 ① — "충돌은 vector clock으로 해결한다"

### 책의 입장
복제본이 갈라지면(AP의 필연) [vector clock]으로 ancestor/sibling을 판정하고, sibling이면 두 버전을 클라이언트에 줘서 머지(장바구니 union)한다.

### 현실의 배신

**(a) Cassandra는 처음부터 vector clock을 안 썼다 — LWW(Last-Write-Wins) 선택**
- 모든 mutation에 timestamp를 찍고 **최신 timestamp가 이긴다**. vector clock 미구현은 **초기에 성능을 이유로** 내린 결정.
- 대신 row를 **column 단위로 쪼개 독립적으로 머지** → vector clock이 풀려던 문제를 데이터 모델로 우회.
- 대가: LWW는 **"정보를 비결정적으로 파괴하는, 별로 좋지 않은 CRDT"**(잃는 쓰기 발생)라는 비판.
- 출처: [Why Cassandra Doesn't Need Vector Clocks — DataStax](https://www.datastax.com/blog/why-cassandra-doesnt-need-vector-clocks), [The trouble with timestamps — Kyle Kingsbury(aphyr)](https://aphyr.com/posts/299-the-trouble-with-timestamps)

**(b) Riak은 vector clock을 노출했다가 CRDT로 갈아탔다**
- sibling 충돌을 **개발자가 직접 머지**해야 하는 부담이 너무 컸다.
- Riak 2.0은 **CRDT(Data Types)** 도입 — 공식 표현: *"개발자가 다시는 sibling 머지 함수를 짤 필요가 없게"*, 수렴 책임을 **앱 → DB로 흡수**.
- 출처: [Distributed Data Types – Riak 2.0](https://riak.com/distributed-data-types-riak-2-0/), [Applied Monotonicity: A Brief History of CRDTs in Riak — C. Meiklejohn](https://christophermeiklejohn.com/erlang/lasp/2019/03/08/monotonicity.html)

**(c) 그래서 후계자는 CRDT (Conflict-free Replicated Data Type)**
- 발상의 전환: "충돌을 **감지해서 클라이언트에 떠넘기는**" 대신, **"자료구조 자체가 충돌 없이 합쳐지도록"** 머지 의미를 내장.
- 예: G-Counter, OR-Set, LWW-Register. 장바구니를 OR-Set으로 만들면 vector clock 없이 union이 자동.
- 현장: 협업 편집(Figma·Notion), Redis CRDT, Automerge.

> **토론 포인트**: vector clock은 "이론적으로 옳지만 운영이 무거운" 전형. 정답이 항상 채택되는 건 아니다.

---

## 2. 책의 주장 ② — "분산 일관성은 CAP으로 결정한다"

### 책의 입장
네트워크 파티션은 필연 → **CP냐 AP냐** 둘 중 하나.

### 한 칸 더: PACELC (CAP의 확장)
- CAP은 **파티션이 났을 때**만 말한다. 그런데 **평소(파티션 없을 때)에도** 복제가 있으면 **Latency vs Consistency** 트레이드오프가 존재한다.
- **PACELC**: "**P**artition이면 **A**/**C**, **E**lse면 **L**atency/**C**onsistency."
- 분류가 더 정밀해진다:
  - **PA/EL**: DynamoDB, Cassandra (파티션 시 가용성, 평소엔 저지연)
  - **PC/EC**: Google Spanner, CockroachDB (항상 강한 일관성)
- 제안자: **Daniel Abadi**(예일대), 2010 블로그 → 2012 논문 *"Consistency Tradeoffs in Modern Distributed Database System Design: CAP is Only Part of the Story"*.
- 출처: [PACELC 논문(2012)](https://www.researchgate.net/publication/220476540_Consistency_Tradeoffs_in_Modern_Distributed_Database_System_Design_CAP_is_Only_Part_of_the_Story), [PACELC — Wikipedia](https://en.wikipedia.org/wiki/PACELC_design_principle)

> **한 줄 효과**: "CAP 중 뭘 골랐냐"가 아니라 **"파티션 시 X, 평소엔 Y"**로 답하면 시스템 성격이 정확히 잡힌다.

---

## 3. 책의 주장 ③ — "Dynamo가 분산 KV의 모범 아키텍처다"

### 책의 입장
leaderless + consistent hashing + quorum + vector clock + gossip + Merkle tree. 이게 Dynamo이고 곧 표준.

### 현실의 배신: 원조마저 그 설계를 떠났다
- **DynamoDB(2012 AWS 서비스)는 Dynamo(2007 논문)와 다른 시스템이다.** USENIX ATC 2022 논문(저자 다수가 AWS 엔지니어)이 **명시**: *"DynamoDB의 아키텍처는 2007 Dynamo와 별로 공유하는 게 없다."*
- 결정적 차이: **DynamoDB는 복제에 MultiPaxos를 쓴다** → 즉 **leader 기반**. Dynamo의 leaderless·vector-clock 모델과 사실상 정반대.
- 규모 근거(설득력용): 2021 Prime Day에 **초당 8,920만 요청** 피크.
- 출처: [Amazon DynamoDB (USENIX ATC 2022) PDF](https://www.usenix.org/system/files/atc22-elhemali.pdf), [The DynamoDB paper — Marc Brooker(저자) 블로그](https://brooker.co.za/blog/2022/07/12/dynamodb.html)

> **토론 포인트**: "leaderless가 우아하다"는 2007년의 미감. 매니지드 서비스로 10년 운영해보니 **예측 가능한 성능·강한 일관성 옵션**을 위해 leader 기반으로 회귀했다.

---

## 4. (보너스) "sloppy quorum도 W+R>N이면 안전하다"는 거짓

- 책/직관: `W+R>N`이면 읽기·쓰기 집합이 **반드시 겹쳐서** 강한 일관성.
- 함정: 이 보장은 **strict quorum일 때만** 성립. sloppy quorum은 임시 대리 노드가 끼어 **읽기·쓰기 노드 집합이 겹치지 않을 수 있다** → `W+R>N`이어도 **stale read 가능**.
- Martin Kleppmann은 이를 **"not really a quorum"**이라 표현(*Designing Data-Intensive Applications*, Ch.5).
- 출처: [DDIA Ch.5 정리 — timilearning](https://timilearning.com/posts/ddia/part-two/chapter-5/)

---

## 5. 한 장 요약 (화이트보드용)

```
책(2007 Dynamo)            현실(2012~)
─────────────────────────────────────────────
vector clock으로 충돌 해결  → Cassandra: LWW
                            → Riak: CRDT로 이주
                            → 후계자 = CRDT (머지 내장)

CAP으로 일관성 결정         → PACELC (평소엔 Latency vs Consistency)
                              PA/EL: Dynamo·Cassandra
                              PC/EC: Spanner·CockroachDB

Dynamo = 모범 아키텍처      → DynamoDB(2022): MultiPaxos, leader 기반
                              "2007 Dynamo와 공유점 거의 없음"

W+R>N → strong             → sloppy quorum이면 깨짐 (stale 가능)
```

## 6. 던질 질문들 (토론용)

1. "이론적으로 옳은" vector clock이 왜 운영에서 졌나? 복잡도를 어디로 옮겨야 하나(클라이언트 vs DB vs 자료구조)?
2. 우리 회사 데이터(MySQL + ES)는 PACELC로 분류하면 각각 뭔가? 결제는? 검색은?
3. 원조 Amazon이 leaderless를 버리고 Paxos로 간 건, "분산은 우아함보다 예측가능성"이라는 신호일까?

---

## 출처 모음 (1차/권위 위주)

- [Why Cassandra Doesn't Need Vector Clocks — DataStax](https://www.datastax.com/blog/why-cassandra-doesnt-need-vector-clocks)
- [Dynamo — Apache Cassandra 공식 문서](https://cassandra.apache.org/doc/latest/cassandra/architecture/dynamo.html)
- [The trouble with timestamps — Kyle Kingsbury(aphyr)](https://aphyr.com/posts/299-the-trouble-with-timestamps)
- [Distributed Data Types – Riak 2.0](https://riak.com/distributed-data-types-riak-2-0/)
- [Applied Monotonicity: A Brief History of CRDTs in Riak — C. Meiklejohn](https://christophermeiklejohn.com/erlang/lasp/2019/03/08/monotonicity.html)
- [PACELC 논문(2012) — Daniel Abadi](https://www.researchgate.net/publication/220476540_Consistency_Tradeoffs_in_Modern_Distributed_Database_System_Design_CAP_is_Only_Part_of_the_Story)
- [PACELC — Wikipedia](https://en.wikipedia.org/wiki/PACELC_design_principle)
- [Amazon DynamoDB (USENIX ATC 2022) PDF](https://www.usenix.org/system/files/atc22-elhemali.pdf)
- [The DynamoDB paper — Marc Brooker 블로그](https://brooker.co.za/blog/2022/07/12/dynamodb.html)
- Martin Kleppmann, *Designing Data-Intensive Applications*, Ch.5 "Replication" — Sloppy Quorums 절
- (원전) Giuseppe DeCandia et al., *Dynamo: Amazon's Highly Available Key-value Store*, SOSP 2007
