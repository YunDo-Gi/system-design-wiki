---
type: tech
category: proxy
sources: [ch01]
---

# DNS (Domain Name System)

## 한 줄 정의

도메인 이름을 IP 주소로 변환해주는 인터넷의 분산 디렉터리 서비스 (ch01, p.16, p.31).

## 주요 특성

- 사용자는 도메인 이름으로 접근, DNS가 [[load-balancer]]의 public IP 등으로 해석.
- **geoDNS**: 요청자의 위치 기반으로 서로 다른 IP를 반환 → [[multi-data-center]]의 트래픽 라우팅 핵심 메커니즘 (ch01, p.31).
- **TTL**: 응답을 클라이언트·리졸버가 캐싱하는 기간. TTL 짧으면 빠른 변경 반영, 길면 부하·지연 감소.
- DNS 자체는 가용성·성능에 크리티컬한 의존점이므로 SPOF가 되지 않도록 멀티 provider·자체 anycast 운영.

## 전형적 사용 사례

- 도메인 → IP 해석 (모든 다이어그램의 첫 화살표).
- geoDNS 기반 글로벌 트래픽 라우팅.
- DNS 기반 페일오버(헬스체크 + 가중치 라우팅).

## 등장 사례

- ch01 — 모든 사용자 진입 지점 다이어그램(Figures 1-3, 1-4, 1-6, 1-11, 1-14, 1-15)에서 등장. [[multi-data-center]] 절에서 geoDNS로 다시 한 번 부각된다.
