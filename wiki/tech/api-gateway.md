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

## 언제 선택하는가 / 대안 비교

| 후보 | 특성 | 적합 |
|---|---|---|
| **매니지드** (AWS API Gateway, GCP API Gateway, Cloudflare API Shield) | 운영 부담 ↓, 기능 제한 가능 | 빠른 출시, 운영 인력 ↓ |
| **Self-host** (Kong, Tyk, Envoy + plugin) | 자유도 ↑, 기능 풍부 | 정교한 정책·내부 통합 |
| **Service mesh** (Istio, Linkerd) | 내부 east-west 트래픽 제어 | 마이크로서비스 내부 정책 |
| **BFF (Backend for Frontend)** | 클라이언트별 별도 게이트웨이 | 모바일·웹 응답 형태가 크게 다를 때 |
| **자체 미들웨어** (앱 내 reverse proxy) | 최대 통제 | 매우 작은 시스템 또는 매우 특수한 요구 |

대형 시스템은 흔히 **API Gateway (north-south) + Service Mesh (east-west)** 조합.

## 전형적 사용 사례

- **마이크로서비스 단일 진입점**: 외부에는 게이트웨이만 노출, 내부 서비스는 게이트웨이를 통해서만 접근 ([[load-balancer]]가 만든 public/private 경계의 응용 계층 확장).
- **rate limit 정책 강제** (ch04, p.58): 자체 구현이 부담스러우면 게이트웨이의 내장 rate limit를 활용.
- BFF(Backend for Frontend) 패턴과 결합해 클라이언트별 응답 조립.
- **인증·인가 일원화**: JWT 검증·OAuth introspection 등을 게이트웨이에서.
- **버전 관리·canary 라우팅**: `/v1`, `/v2` 분기, A/B 테스트.

## 실무 함정

- **단일 진입점 = SPOF**: 게이트웨이 다운이 전 서비스 다운. **active-active HA + 멀티 AZ** 필수. 매니지드 게이트웨이도 region 다운에 대비.
- **비즈니스 로직 침투**: 인증·라우팅·rate limit 같은 횡단 관심사만. **변환·집계·도메인 로직을 게이트웨이로 옮기면 새 모놀리식**이 됨. 책임 경계를 명시.
- **레이턴시 추가**: 한 hop 더. p99 영향 측정. 게이트웨이의 plugin 체인이 길수록 누적.
- **알고리즘·정책의 한계**: 매니지드는 내장 rate limit 알고리즘이 정해져 있어 token bucket·sliding window 같은 정교한 정책이 제한될 수 있음.
- **설정의 폭주**: 라우팅·정책·플러그인이 누적되면 게이트웨이 설정 자체가 복잡한 시스템. **IaC로 관리**·**리뷰 절차**·**스테이징 검증** 필수.
- **장애 격리 부재**: 한 서비스가 게이트웨이 자원을 폭주시키면 다른 서비스로 전파. **per-service 자원 격리** (bulkhead)·**circuit breaker** 도입.
- **벤더 락-인**: AWS API Gateway 전용 변수·통합은 다른 클라우드로 이식 어려움. 핵심 로직은 게이트웨이 밖으로.
- **로깅·관측성**: 게이트웨이 로그는 보안·운영의 1차 정보. 누락되면 사후 분석 불가. **request_id 전파**·**trace propagation** (W3C Trace Context).
- **인증 캐시**: 매 요청 토큰 검증은 비싸므로 짧은 캐시. 그러나 revoke 반영 지연 발생.

## 등장 사례

- ch04 — rate limiter 배치 위치 선택지로 도입. "이미 마이크로서비스 + API gateway가 있다면 rate limit도 거기 얹는 게 자연스럽다"는 가이드라인 제시.
- ch03 News Feed 예제의 web server에 표기된 "Authentication / Rate Limiting"도 사실상 API gateway 역할의 일부.
