---
type: concept
tags: [scalability, architecture, session]
sources: [ch01]
---

# 무상태 웹 티어 (Stateless Web Tier)

## 한 줄 정의

각 web server가 클라이언트 상태(세션·프로필 이미지 등)를 자신의 메모리/디스크에 갖지 않고 **공유 저장소**에서 매 요청마다 가져오도록 만든 아키텍처 (ch01, p.27-29).

## 왜 필요한가

stateful 구조에서는 사용자 A의 요청이 반드시 그의 상태를 가진 서버로만 가야 하므로 **sticky session**이 필요하다 (ch01, p.28). 이는:

- 로드 밸런서 오버헤드 증가.
- 서버 추가·제거가 어려움 (오토스케일링 실패).
- 서버 1대 다운 시 그 서버에 묶인 사용자들이 영향 받음.

무상태로 만들면 [[load-balancer]]는 임의 서버로 요청을 보내도 되고, 오토스케일링·failover가 자연스럽게 동작한다.

## 핵심 메커니즘

- **세션 외부화**: 세션 데이터를 RDB / [[memcached]] / [[redis]] / [[nosql-database]] 같은 공유 저장소로 이동 (ch01, p.29, Figure 1-14).
- NoSQL이 자주 선택되는 이유: 쉽게 수평 확장됨.
- 각 web server는 요청을 받을 때마다 저장소에서 state를 fetch → 응답 후 잊는다.

## 트레이드오프

- **장점**: 단순, 견고, 확장 가능. 오토스케일링과 궁합이 좋음.
- **비용**: 세션 저장소 자체가 새로운 중요 컴포넌트 — 가용성·지연시간을 챙겨야 한다. 매 요청 추가 round-trip이 발생할 수 있어 캐싱 전략(예: 토큰 기반 JWT)으로 줄이기도 한다.

## 등장 사례

- ch01 — [[database-replication]] 도입 직후, 수평 확장의 전제로 무상태 web tier가 등장. 이후 [[multi-data-center]]·오토스케일링의 기반이 된다.
