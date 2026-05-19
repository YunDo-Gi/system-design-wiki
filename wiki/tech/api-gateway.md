---
type: tech
category: proxy
sources: [ch04]
---

# API 게이트웨이 (API Gateway)

## 한 줄 정의

클라이언트와 백엔드 마이크로서비스 사이에 놓여 인증·SSL termination·rate limiting·IP whitelisting·정적 콘텐츠 서빙 등을 일괄 처리하는 완전관리형 미들웨어 (ch04, p.58).

## 주요 특성

- **횡단 관심사(cross-cutting concerns) 통합**: 모든 서비스가 직접 구현할 필요 없는 기능을 한 군데에 모음.
- 대표 기능: rate limiting, **SSL/TLS termination**, authentication, IP whitelisting, **request routing**, response 변환, 정적 콘텐츠 서빙, 로깅·모니터링.
- 매니지드 옵션(예: AWS API Gateway, GCP API Gateway, Kong, Apigee) 또는 self-host(Kong, Tyk, Envoy 기반).
- [[load-balancer]]보다 한 단계 더 응용 계층에 가까운 동작. L7 라우팅·정책 적용이 핵심.

## 전형적 사용 사례

- **마이크로서비스 단일 진입점**: 외부에는 게이트웨이만 노출, 내부 서비스는 게이트웨이를 통해서만 접근 ([[load-balancer]]가 만든 public/private 경계의 응용 계층 확장).
- **rate limit 정책 강제** (ch04, p.58): 자체 구현이 부담스러우면 게이트웨이의 내장 rate limit를 활용.
- BFF(Backend for Frontend) 패턴과 결합해 클라이언트별 응답 조립.

## 트레이드오프 / 함정

- **단일 진입점이 곧 [[single-point-of-failure]]** 위험 — 게이트웨이 자체를 이중화·HA 구성 필수.
- 매니지드 게이트웨이는 빠르지만 **rate limit 알고리즘 선택지가 제한될 수 있음** — 정교한 정책이 필요하면 application-level 구현이 더 자유롭다 (ch04, p.59).
- 게이트웨이에 비즈니스 로직을 너무 많이 넣으면 새로운 모놀리식으로 변질.

## 등장 사례

- ch04 — rate limiter 배치 위치 선택지로 도입. "이미 마이크로서비스 + API gateway가 있다면 rate limit도 거기 얹는 게 자연스럽다"는 가이드라인 제시.
- ch03 News Feed 예제의 web server에 표기된 "Authentication / Rate Limiting"도 사실상 API gateway 역할의 일부.
