---
type: concept
tags: [traffic, security, availability]
sources: [ch04, ch10]
---

# 처리율 제한 (Rate Limiting)

## 한 줄 정의

클라이언트나 서비스가 일정 기간 안에 보낼 수 있는 요청 수를 임계치로 제한하고, 초과분은 차단·지연시키는 트래픽 제어 기법 (ch04, p.55).

## 왜 필요한가

세 가지 동기 (ch04, p.55):

1. **자원 고갈 방지**: 의도적(DoS)·비의도적 트래픽 폭주를 막아 정상 사용자 보호. Twitter는 3시간당 300트윗, Google Docs API는 사용자당 60초 300 read 제한이 디폴트.
2. **비용 절감**: 외부 유료 API (결제·신용·헬스 등) 호출 수를 제한해 과금 통제.
3. **서버 과부하 방지**: 봇·악성 사용자 트래픽을 거른다.

## 핵심 메커니즘

### 어디에 둘 것인가 (ch04, p.57-59)

| 위치 | 특징 |
|---|---|
| Client | 위·변조 쉬워서 **단독 사용 비추천**. 추가 방어선 정도. |
| Server-side | 표준. 알고리즘 자유도 ↑, 구현 책임도 본인 |
| **API gateway 미들웨어** | rate limit + SSL + auth + IP whitelist 묶음 — microservices 환경 기본 |

선택 기준: 기존 스택·인력 여력·알고리즘 통제 필요성. microservices에 이미 [[api-gateway]]가 있으면 거기 얹는 게 자연스러움.

### 어떤 알고리즘 (ch04, p.59-65)

5종 비교:

- [[token-bucket-algorithm]] — 버스트 허용, AWS/Stripe.
- [[leaking-bucket-algorithm]] — FIFO, 일정 outflow, Shopify.
- [[fixed-window-counter-algorithm]] — 단순, 경계 burst 취약.
- [[sliding-window-log-algorithm]] — 정확, 메모리 비쌈.
- [[sliding-window-counter-algorithm]] — 근사·메모리 효율, Cloudflare 0.003% 오차.

### 어떻게 응답할 것인가 (ch04, p.69)

- HTTP **429 Too Many Requests**.
- 헤더: `X-Ratelimit-Limit` (창당 허용), `X-Ratelimit-Remaining` (남은 수), `X-Ratelimit-Retry-After` (재시도까지 초).
- 사용 사례에 따라 drop 대신 **메시지 큐 enqueue**로 후처리도 가능.

## 트레이드오프

- **Hard vs soft**: hard = 임계 초과 절대 불가, soft = 단기 초과 허용. 사용자 경험 vs 보호 강도.
- **OSI 레이어**: 본 책은 layer 7 (HTTP). layer 3에서는 `iptables`로 IP 차단. 레이어가 낮을수록 비용은 싸지만 식별 정밀도 ↓.
- **클라이언트 모범 사례**: 응답 캐시로 호출 줄이기, 한도 인지, 예외 처리, 충분한 **exponential backoff**.

## 실무 적용 시 고려사항

- **식별 차원의 다중화**: "사용자별" 만으로는 부족. 익명 트래픽엔 IP, 로그인 시도엔 IP + username, B2B엔 API key. **차원별 별도 정책**을 묶어 적용 (예: per-user AND per-IP).
- **점진적 응답 강화**: 임계 도달 즉시 429보다 **softening** 단계 추가 — 캡차, 응답 지연, 비용 안내. UX 보호.
- **공격자 vs 정상 사용자 구분**: 단일 임계치는 양쪽을 같이 막음. 행동 패턴(요청 다양성·세션 길이) 기반 가중치로 보완.
- **출시·캠페인 직후 모니터링**: 새 한도로 정상 사용자 다수 차단되는 경우가 흔함. 출시 첫 N일은 "관찰만"(observation-only) 모드로 데이터 수집 후 임계치 조정.
- **분산 환경의 일관성**: 카운터를 [[redis]] 같은 중앙 저장소에 두고, 노드 간 sticky session 없이 운영. race condition은 Lua/sorted set으로 해결.
- **우회 방지**: 클라이언트가 IP 변경·계정 다중 생성으로 회피 가능. 행동 분석·디바이스 핑거프린팅과 결합.
- **운영 가시화**: 임계 도달률·차단된 사용자 분포·재시도 패턴을 대시보드로. SRE의 일상 점검 항목.
- **법적·정책적 함의**: 일부 도메인(공공 데이터, 금융)은 차별·차단 정책이 규제 대상. 차단 이유·재시도 안내를 명확히 응답에 포함.

## 등장 사례

- ch04 — 장 전체 주제.
- ch03 News Feed 예제 다이어그램에서도 web server 영역에 "Rate Limiting"이 인증과 함께 표기됨 — 일반 미들웨어 위치를 시사.
