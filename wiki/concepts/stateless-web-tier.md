---
type: concept
tags: [scalability, architecture, session]
sources: [ch01, ch11, ch14]
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

## 실무 적용 시 고려사항

- **JWT vs 서버 세션**: 서버에 저장 없이 토큰 자체에 클레임을 박는 JWT는 round-trip을 0으로 줄이지만 **revoke가 어렵다**(짧은 만료 + refresh token 패턴이 표준). 민감 세션은 여전히 서버 측 세션 저장소가 안전.
- **세션 저장소 가용성**: 세션 저장소 자체가 새 [[single-point-of-failure]]가 된다. [[redis]] cluster·replica, 멀티 AZ 배포 등으로 이중화.
- **부분 stateful 흐름의 분리**: 파일 업로드 중간 상태·실시간 스트리밍 같은 부분은 본질적으로 stateful — 별도 서비스(S3 multipart upload, WebSocket gateway)로 분리하고 web tier는 계속 stateless 유지.
- **로컬 캐시는 stateless를 깨지 않는가**: in-memory 캐시(메모이즈)는 stateless 원칙과 충돌하지 않음(read-only). 단 사용자별 데이터를 in-memory에 두면 안 됨.
- **로컬 디버깅용 임시 sticky session**: 카나리 배포·일부 WebSocket 핸드셰이크에서만 한정 사용. 일반 트래픽엔 적용 금지.
- **CSRF·CORS 영향**: 세션을 외부 토큰으로 옮기면 인증 헤더 전송 패턴이 바뀌므로 CORS·CSRF 정책 재검토 필요.

## 등장 사례

- ch01 — [[database-replication]] 도입 직후, 수평 확장의 전제로 무상태 web tier가 등장. 이후 [[multi-data-center]]·오토스케일링의 기반이 된다.
- ch04 — rate limiter 분산 환경에서 sticky session 대신 중앙 [[redis]] 사용을 권장하는 동일 원칙.
