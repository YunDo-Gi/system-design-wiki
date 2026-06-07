---
type: concept
tags: [distributed-systems, conflict-resolution, replication, data-structure, algorithm]
sources: [ch06]
---

# CRDT (Conflict-free Replicated Data Type)

## 한 줄 정의 / 동기

복제본이 갈라져도 **충돌을 사후에 해결하지 않고**, merge 연산을 수학적으로 잘 설계해 **어떤 순서·중복으로 변경을 받아도 같은 값으로 수렴**하게 만든 자료구조 계열. 중앙 조율(합의) 없이 **Strong Eventual Consistency(SEC)** 를 달성한다 (Shapiro et al., INRIA 2011).

[[vector-clock]]이 충돌을 *감지*해 클라이언트에 떠넘기고, [[consistency-models|LWW]]가 timestamp로 한쪽을 *버리는* 것과 달리, CRDT는 **"충돌이 불가능한 구조"로 회피**한다. 책(ch06)에는 없지만 vector clock의 사실상 후계 개념.

## 동작

### 수렴이 보장되는 이유 — 세 성질

merge(⊕)를 다음 셋을 만족하게 설계한다:

| 성질 | 식 | 분산 환경에서의 의미 |
|---|---|---|
| 교환법칙 (commutative) | `a⊕b = b⊕a` | 변경을 **어떤 순서**로 받아도 같은 결과 |
| 결합법칙 (associative) | `(a⊕b)⊕c = a⊕(b⊕c)` | **묶는 방식**이 달라도 같은 결과 |
| 멱등성 (idempotent) | `a⊕a = a` | 같은 메시지를 **중복 수신**해도 안전 |

분산 네트워크에서 메시지는 순서가 뒤바뀌고, 중복 도착하고, 재전송된다. 세 성질을 만족하면 그 모든 상황에서 결과가 흔들리지 않는다. 수학적으로 이 구조는 **join semilattice(반격자)** 이고, merge는 항상 상한(least upper bound)으로만 올라가는 연산이라 수렴이 증명된다.

### 타입별 동작

**G-Counter (Grow-only Counter)** — 복제본별 카운트 맵으로 보관:

```
state = { A:3, B:5, C:2 }       value = sum = 10

increment(self):  state[self] += 1          # 자기 칸만 증가
merge(x, y):      ∀k. result[k] = max(x[k], y[k])   # 칸별 최댓값
value():          sum(state.values())
```

`max`가 교환·결합·멱등 → 어떤 순서로 합쳐도 같은 값, 증가가 하나도 유실되지 않음.

```
A: {A:3, B:5}      B: {A:1, B:7}
merge → {A:3, B:7}  (칸별 max) → value 10
```

**PN-Counter** — 증가용·감소용 G-Counter 두 개. `value = sum(P) − sum(N)`. 감소를 음수 증가로 직접 넣으면 max가 깨지므로 분리하는 트릭.

**OR-Set (Observed-Remove Set)** — 실전용 집합. 추가마다 **고유 태그**를 붙이는 게 핵심:

```
A: add(apple) → {apple#a1}
B: add(apple) → {apple#b1}      # 서로 다른 태그
A: remove(apple) → 자기가 본 태그 a1만 제거

merge 후: apple#b1 생존 → apple 살아있음  (add-wins)
```

동시 추가·삭제 시 **추가가 이긴다.** "방금 담았는데 다른 곳에서 지워 사라지는" 사고 방지.

**기타**: G-Set(추가만, merge=합집합), 2P-Set(추가/삭제 집합, 한 번 지우면 재추가 불가), LWW-Register(값+timestamp, merge=늦은 쪽 — LWW도 merge가 정의된 가장 단순한 CRDT의 일종), Sequence/텍스트 CRDT(RGA·Yjs — 글자마다 순서 있는 고유 ID로 동시 편집 병합).

### 두 가지 구현 방식

| | State-based (CvRDT) | Operation-based (CmRDT) |
|---|---|---|
| 전파 | 전체 상태를 주고받아 merge | 연산(op)만 브로드캐스트 |
| 요구 | merge가 교환·결합·멱등 (semilattice) | op끼리 교환 가능 + 신뢰성 있는 전달(보통 인과 순서) |
| 장점 | 유실·중복에 강함(멱등) | 대역폭 적음 |
| 단점 | 상태 통째 전송이라 무거움 | 전달 보장 인프라 필요 |

## 파라미터 · 튜닝 포인트

| 포인트 | 영향 |
|---|---|
| State-based vs Op-based | 대역폭 vs 전달 보장 요구. delta-state CRDT로 절충(변경분만 전송) |
| Tombstone GC 정책 | 삭제 흔적(tombstone)을 언제 정리할지. 너무 빨리 지우면 정확성 깨짐, 안 지우면 부풀음 |
| add-wins vs remove-wins | OR-Set은 add-wins. 도메인에 맞는 의미 선택 |
| 태그/메타데이터 인코딩 | 복제본 식별자·버전 크기 — 노드 많으면 메타데이터 비용↑ |

## 트레이드오프

**Pros**
- **합의·조율 없이 수렴** — leaderless·오프라인·고지연 환경에서 강함.
- **클라이언트 머지 로직 불필요** — 자료구조가 알아서 합침([[vector-clock]] 대비).
- **데이터 유실 없음** — LWW와 달리 동시 변경을 버리지 않음.

**Cons**
- **메타데이터 누적**: 태그·tombstone·복제본별 맵이 쌓이고, 정확성 때문에 GC가 어렵다 → 장기적으로 부풀음.
- **정의된 타입에서만**: 카운터·집합·맵·텍스트는 되지만 **임의 비즈니스 규칙은 불가**.
- **불변식(invariant) 표현 불가**: "잔고 ≥ 0" 같은 제약은 CRDT로 못 지킨다 — 두 복제본에서 동시 출금하면 각자 OK 후 합치면 음수. 이런 건 강한 일관성(합의) 필요.
- **머지 의미가 고정**: 자동이라는 건 "내가 못 고른다"는 뜻이기도. add-wins가 직관과 어긋날 수 있음.

**선택 기준**: AP·오프라인 우선 + 데이터 타입이 카운터/집합/텍스트로 표현됨 + 강한 불변식이 불필요할 때. 강한 제약·트랜잭션이 필요하면 합의 기반으로.

## 다른 알고리즘과의 위치

| 기법 | 충돌 처리 | 머지 책임 | 데이터 유실 |
|---|---|---|---|
| **LWW** | timestamp 비교 | DB(고정 규칙) | 있음(진 쪽 소멸) |
| **[[vector-clock]]** | 인과관계 감지 | 클라이언트(도메인 머지) | 없음(둘 다 반환) |
| **CRDT** | 구조적으로 회피 | 자료구조(내장 규칙) | 없음(타입이 정의) |
| **합의(Paxos/Raft)** | 사전 차단(단일 순서) | 시스템(선형화) | 없음(단, 가용성↓) |

계보로 보면 LWW의 유실 → vector clock(감지)으로, vector clock의 클라이언트 부담 → CRDT(자동 머지)로 옮겨 온 흐름.

## 실무 적용 시 고려사항

- **tombstone/메타데이터 모니터링**: OR-Set 태그, 삭제 tombstone, 버전 메타데이터의 증가율을 지켜보고 GC·compaction 전략을 둔다.
- **delta-state CRDT**: 전체 상태 대신 변경분(delta)만 전파해 state-based의 대역폭 문제 완화.
- **타입 매핑 설계**: 도메인 데이터를 어떤 CRDT 타입으로 표현할지가 곧 설계. 장바구니=OR-Set, 좋아요 수=PN-Counter, 문서=Sequence CRDT.
- **불변식은 밖에서**: CRDT가 못 지키는 제약(재고 음수 방지 등)은 별도 강한 일관성 경로로 처리.
- **라이브러리 활용**: 직접 구현보다 검증된 구현 사용 — Automerge·Yjs(텍스트/JSON), Riak Data Types, Redis(CRDB).

## 다른 개념과의 관계

- [[vector-clock]] — CRDT가 대체한 직전 세대. 충돌 감지까지만 하고 머지는 클라이언트.
- [[consistency-models]] — CRDT는 Strong Eventual Consistency를 제공하는 도구.
- [[quorum-consensus]] — N/W/R로 충돌 발생률을 낮추는 것과 달리, CRDT는 충돌이 나도 무손실 수렴.
- [[cap-theorem]] — AP 시스템에서 일관성 약화의 비용을 자료구조로 흡수.

## 등장 사례

- ch06 — 책 본문엔 없으나 [[vector-clock]] 충돌 해결의 후계 개념으로 직접 연결.
- **Riak** — Data Types(2.0)로 vector clock 머지 부담을 CRDT로 흡수.
- **Redis** — Active-Active(CRDB)가 CRDT 기반 지역 간 복제.
- **Figma·Notion·Google Docs, Automerge, Yjs** — 실시간 협업 편집의 Sequence/JSON CRDT.
- **Riak·Phoenix Presence(Elixir)** — OR-Set 등 실전 사용.

## 참고 문헌

- Marc Shapiro, Nuno Preguiça, Carlos Baquero, Marek Zawirski, "Conflict-free Replicated Data Types", INRIA RR-7687, 2011.
- [Distributed Data Types – Riak 2.0](https://riak.com/distributed-data-types-riak-2-0/)
- [A Brief History of CRDTs in Riak — Christopher Meiklejohn](https://christophermeiklejohn.com/erlang/lasp/2019/03/08/monotonicity.html)
