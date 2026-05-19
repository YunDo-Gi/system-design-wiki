---
type: tech
category: proxy
sources: [ch01]
---

# 로드 밸런서 (Load Balancer)

## 한 줄 정의

들어오는 트래픽을 사전에 정의된 web server 풀에 고르게 분배하는 네트워크 컴포넌트 (ch01, p.19).

## 주요 특성

- **Public IP** 하나를 외부에 노출, 내부 서버는 **private IP**로 통신 → 보안 경계 형성 (ch01, p.19, Figure 1-4).
- **failover**: 한 서버 다운 시 트래픽을 다른 서버로 자동 우회.
- **수평 확장 지원**: 풀에 서버를 추가하면 LB가 자동으로 트래픽 분배.
- 분산 알고리즘: round-robin, least-connections, weighted, IP-hash 등 (책에선 깊이 다루지 않음).
- 계층: L4(TCP) vs L7(HTTP). HTTP 헤더·쿠키 기반 라우팅은 L7.
- **sticky session** 기능 — 운영 부담이 커 [[stateless-web-tier]] 선호 (ch01, p.28).

## 전형적 사용 사례

- web tier 앞단의 표준 배치.
- API gateway·SSL termination 지점으로도 자주 사용.
- [[multi-data-center]] 구성에서 DC간 트래픽 분배.

## 등장 사례

- ch01 — single web server의 가용성 문제(failover 없음, 과부하)를 해결하기 위해 가장 먼저 도입되는 컴포넌트. 이후 거의 모든 ch01 아키텍처 다이어그램의 정문 역할.
