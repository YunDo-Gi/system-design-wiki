---
type: tech
category: proxy
sources: [ch01, ch11]
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

## 언제 선택하는가 / 대안 비교

| 후보 | 특성 | 적합 |
|---|---|---|
| **L4 LB** (TCP/UDP, HAProxy·NLB) | 빠름, 프로토콜 무관, 헤더 모름 | gRPC, DB 프록시, 단순 분산 |
| **L7 LB** (HTTP, ALB·NGINX) | 헤더·쿠키·경로 기반 라우팅, SSL termination | 웹 API, A/B 테스트, canary |
| **DNS 기반** ([[dns]] round-robin) | 인프라 단순, TTL 의존 | 글로벌 DC 진입점 |
| **Anycast** | BGP 라우팅, 가장 가까운 노드 | CDN edge·DNS·DoS 흡수 |
| **클라이언트 측 LB** (gRPC) | LB 컴포넌트 자체 제거 | service mesh, 내부 RPC |

대부분의 실시스템은 **여러 LB를 계층화** — DNS → anycast/edge → L7 ALB → 내부 service mesh.

## 전형적 사용 사례

- web tier 앞단의 표준 배치.
- API gateway·SSL termination 지점으로도 자주 사용.
- [[multi-data-center]] 구성에서 DC간 트래픽 분배.

## 실무 함정

- **Health check 정확성**: TCP만 보면 프로세스는 살아 있지만 DB·캐시 의존성이 끊긴 좀비 서버를 통과시킴. **HTTP health endpoint**가 안전 — 단, 의존성 전체를 체크하면 cascade failure 발생 가능(절충).
- **Slow start / connection draining**: 새 서버는 캐시·JIT 워밍 시간이 필요 → 트래픽을 점진적으로 (slow-start). 종료 시엔 graceful drain으로 in-flight 요청 보호.
- **LB 자체가 SPOF**: 단일 LB는 안 됨. active-active(ELB/ALB는 내부적으로 다중) 또는 anycast로 이중화.
- **Sticky session 남용**: 디버깅·일부 WS 핸드셰이크에서만. 일반 트래픽은 [[stateless-web-tier]]로.
- **TLS termination 위치**: LB에서 종료하면 내부는 평문 → VPC 보안 정책 필요. 또는 LB에서 패스스루 후 backend가 직접 처리.
- **세션 timeout / idle timeout**: LB의 idle timeout이 백엔드보다 짧으면 long-polling·SSE·WebSocket 연결이 끊김. 명시적 조정 필수.
- **불균등 분산**: round-robin은 요청 비용을 모름 → 일부 서버 폭주. **least-connections** 또는 **weighted random**으로 보완.

## 등장 사례

- ch01 — single web server의 가용성 문제(failover 없음, 과부하)를 해결하기 위해 가장 먼저 도입되는 컴포넌트. 이후 거의 모든 ch01 아키텍처 다이어그램의 정문 역할.
