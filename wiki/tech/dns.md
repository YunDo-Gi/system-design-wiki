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

## 언제 선택하는가 / 대안 비교

| 후보 | 특성 | 적합 |
|---|---|---|
| **Route 53 / Cloudflare DNS / NS1** | 매니지드, 헬스체크·geoDNS·가중치 라우팅 | 일반 서비스 |
| **자체 BIND / PowerDNS** | 완전 통제, 운영 부담 | 사내 DNS, 특수 정책 |
| **Anycast DNS** | BGP로 가까운 노드 응답 | 글로벌 저지연 |
| **Service discovery** (Consul, etcd) | 내부 마이크로서비스 동적 등록 | 내부 RPC, K8s 서비스 |

대부분 운영 환경은 **외부 DNS = 매니지드, 내부 = Service discovery** 조합.

## 전형적 사용 사례

- 도메인 → IP 해석 (모든 다이어그램의 첫 화살표).
- geoDNS 기반 글로벌 트래픽 라우팅.
- DNS 기반 페일오버(헬스체크 + 가중치 라우팅).
- 내부 서비스 디스커버리(Consul, Kubernetes DNS).

## 실무 함정

- **TTL의 양날**: 짧으면 빠른 페일오버이지만 트래픽·비용 ↑. 길면 변경 반영 늦음. **평상시 길고 변경 직전에 단축**하는 운영 패턴.
- **클라이언트 측 TTL 무시**: 브라우저·OS·중간 리졸버가 TTL을 자체 정책으로 캐시. 분 단위 페일오버를 DNS만으로는 보장 못함 — anycast나 글로벌 LB로 보완.
- **DNS provider SPOF**: **Dyn DNS 2016** 사건처럼 한 provider 장애가 다수 서비스를 동시에 다운시킴. 멀티 provider 전략(secondary DNS, RFC 2182)이 안전.
- **Split-horizon DNS**: 내부·외부에서 같은 도메인이 다른 IP로 해석되어야 할 때 설정 오류로 leak·접근 실패 발생.
- **DNSSEC 운영 비용**: 키 롤오버·서명 갱신을 자동화 안 하면 검증 실패로 도메인 자체가 안 풀림.
- **음성 응답(negative caching)**: NXDOMAIN·NODATA도 캐싱됨. 새 레코드 추가 직후 일정 시간 안 보일 수 있음.
- **AAAA·HTTPS 레코드 누락**: IPv6·HTTP/3 도입 시 새 레코드 타입을 잊으면 성능 저하·실패.
- **자동화 누락**: DNS는 수동 운영의 잔재가 많은 영역. **terraform/IaC로 관리**하지 않으면 사람 실수 사고가 잦음.
- **TLS 인증서와 동기화**: SAN·CN과 실제 DNS가 어긋나면 HTTPS 실패. 인증서 발급(예: Let's Encrypt DNS-01)이 DNS API에 의존하기도.

## 등장 사례

- ch01 — 모든 사용자 진입 지점 다이어그램(Figures 1-3, 1-4, 1-6, 1-11, 1-14, 1-15)에서 등장. [[multi-data-center]] 절에서 geoDNS로 다시 한 번 부각된다.
