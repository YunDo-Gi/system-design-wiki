---
type: concept
tags: [availability, reliability, fundamentals]
sources: [ch01]
---

# 단일 장애점 (Single Point of Failure, SPOF)

## 한 줄 정의

> "시스템의 한 부분이 고장 나면 시스템 전체가 멈추는 부분." (Wikipedia, ch01 p.24에서 인용)

## 왜 필요한가 (왜 회피해야 하는가)

가용성은 결국 **"가장 취약한 단일 컴포넌트의 가용성"** 으로 결정된다. SPOF를 남겨두면 다른 곳에 아무리 redundancy를 깔아도 시스템 가용성은 그 한 곳에서 무너진다.

## 핵심 메커니즘 — SPOF 후보와 회피책

ch01 전체가 SPOF 제거의 연속이다.

| SPOF 후보 | 회피책 | 참조 |
|---|---|---|
| 단일 web server | LB 뒤 다중 web server | [[load-balancer]] |
| 단일 DB | master/slave 또는 multi-master | [[database-replication]] |
| 단일 cache 노드 | 여러 노드·여러 DC, 메모리 오버프로비저닝 | [[caching-strategies]] |
| 단일 데이터센터 | geoDNS 기반 멀티 DC 액티브-액티브 | [[multi-data-center]] |
| 동기 호출 producer/consumer | 메시지 큐로 비동기 분리 | [[decoupling-with-message-queue]] |
| 단일 web server의 세션 보관 | 세션을 공유 저장소로 | [[stateless-web-tier]] |

## 트레이드오프

- 이중화는 비용·복잡도를 키운다. 가용성 목표(SLA)와 비용 사이의 명시적 트레이드오프가 필요.
- "이중화"가 곧 "독립 장애"는 아니다. 동일 DC·동일 전원·동일 네트워크 스위치를 공유하면 여전히 상관 장애가 발생할 수 있다 — **장애 격리(fault isolation)** 까지 함께 봐야 한다.

## 등장 사례

- ch01 — 캐시 tier 논의에서 SPOF가 명시적으로 정의되고 (Figure 1-8), 이후 모든 확장 단계의 암묵적 동기로 작동한다.
