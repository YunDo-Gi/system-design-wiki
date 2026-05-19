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

## 실무 적용 시 고려사항

- **시스템을 그려놓고 컴포넌트 하나씩 X**: 가장 단순하고 확실한 SPOF 점검법. 각 박스를 가렸을 때 시스템이 어떻게 동작하는지 시뮬레이션해보면 의외의 의존성이 드러난다.
- **숨은 SPOF 후보**: DNS provider, TLS 인증서 발급 기관, 모니터링·로그 시스템, 빌드·배포 파이프라인, 사내 IAM, license 서버. **운영 의존성**이 자주 빠진다.
- **이중화 ≠ 독립 장애**: 두 노드가 같은 랙·전원·스위치·관리자 계정을 공유하면 상관 장애. AZ/리전/공급자 단위로 격리.
- **Cascading failure 방지**: 한 컴포넌트 장애가 폭주로 번지지 않게 ① **circuit breaker** (Hystrix/Resilience4j 류) ② **bulkhead** (thread pool 분리) ③ **timeout + retry budget** ④ **load shedding**.
- **카오스 엔지니어링**: Netflix Chaos Monkey처럼 의도적으로 인스턴스·AZ·종속성을 죽여 SPOF를 발견. 운영 환경에서 정기적으로.
- **DR(disaster recovery) 계획**: 명시적 **RPO**(최대 허용 데이터 손실)·**RTO**(최대 허용 복구 시간) 목표 → 그 목표에 맞는 백업·복제·전환 절차 설계.
- **인적 SPOF**: "이 시스템은 X만 안다"도 SPOF. 문서화·runbook·교차 훈련으로 회피.

## 등장 사례

- ch01 — 캐시 tier 논의에서 SPOF가 명시적으로 정의되고 (Figure 1-8), 이후 모든 확장 단계의 암묵적 동기로 작동한다.
- ch04 — rate limiter 분산 환경에서 단일 카운터 서버가 SPOF가 되지 않게 중앙 [[redis]] 클러스터를 사용.
- Dyn DNS 2016 — DNS provider 한 곳의 장애로 다수 대형 서비스 다운. DNS 단일 의존이 큰 SPOF임을 보인 사례.
