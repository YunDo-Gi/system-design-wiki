---
type: tech
category: cdn
sources: [ch01, ch11, ch13]
---

# 콘텐츠 전송 네트워크 (Content Delivery Network, CDN)

## 한 줄 정의

지리적으로 분산된 서버들이 정적 콘텐츠(이미지·비디오·CSS·JS)를 사용자 근처에서 캐싱·전송하는 네트워크 (ch01, p.24).

## 주요 특성

- **edge 캐싱**: 사용자에게 가까운 PoP에서 서빙 → 지연 단축. 책 예시: SF 사용자 40ms vs LA→유럽 origin 120ms (Figure 1-9).
- **워크플로** (Figure 1-10):
  1. 클라이언트가 CDN 도메인의 URL로 자산 요청.
  2. CDN miss 시 origin(웹서버 또는 S3)에서 가져와 캐싱.
  3. HTTP **TTL** 헤더로 캐싱 기간 결정.
- **무효화 (invalidation)**: 공급자 API로 객체 무효화, 또는 **객체 버저닝** (`image.png?v=2`)으로 새 버전 강제.

## 사용 시 고려사항 (ch01, p.27)

- **비용**: 출입 데이터 전송 과금 — 잘 안 쓰는 자산은 CDN에서 빼는 게 낫다.
- **TTL 설정**: 짧으면 origin 재로딩 빈발, 길면 stale.
- **CDN fallback**: CDN 장애 시 클라이언트가 감지하고 origin에서 받도록 설계.

## 언제 선택하는가 / 대안 비교

| 후보 | 특성 | 적합 |
|---|---|---|
| **공용 CDN** (Cloudflare, CloudFront, Akamai, Fastly) | 글로벌 edge·DDoS 흡수, 매니지드 | 글로벌 정적 자산, 보안 |
| **Origin LB + 짧은 TTL** | 단순, 인프라 작음 | 트래픽 소규모·국지적 |
| **Edge 컴퓨팅** (Cloudflare Workers, Lambda@Edge) | edge에서 코드 실행 | 동적 응답·인증 등 |
| **자체 CDN** | 완전 제어 | 매우 큰 자체 트래픽(Netflix Open Connect 등) |

## 전형적 사용 사례

- 정적 자산 글로벌 배포 (책에서 주로 다루는 범위).
- 동적 콘텐츠 캐싱(쿠키·쿼리·경로 기반)도 가능하지만 본 책 범위 밖.
- **API 응답 캐싱**: 자주 안 바뀌는 GET 엔드포인트에 짧은 TTL + cache-control 헤더.
- **DDoS 흡수·WAF**: 공용 CDN은 보통 보안 기능을 함께 제공.

## 실무 함정

- **Cache key 설계 실수 → 사용자별 데이터 leak**: 쿠키·인증 헤더를 cache key에 포함 안 하면 A 사용자의 응답이 B에게 전달. 인증 후 컨텐츠는 보통 캐싱 금지(`Cache-Control: private`) 또는 사용자 ID를 key에 포함.
- **`Vary` 헤더 누락**: 응답 콘텐츠가 헤더(Accept-Encoding, Accept-Language 등)에 따라 다르면 `Vary`로 알려야 함. 안 그러면 잘못된 응답 캐싱.
- **Purge 비용·전파 지연**: 객체 무효화는 비싸고 즉시 반영 안 됨. **버저닝(`?v=N` 또는 hash 포함 파일명)** 이 더 빠르고 안전.
- **Origin 직접 노출**: 공격자가 origin IP를 알면 CDN 우회 가능. origin은 firewall로 CDN IP만 허용.
- **인증서 관리**: CDN과 origin 양쪽에 별도 인증서. 만료 모니터링 누락이 흔한 사고.
- **Cold cache**: 새 버전 배포 직후 cache miss 폭주로 origin에 부하. **stale-while-revalidate**·**pre-warm**으로 완화.
- **비용**: CDN 트래픽 자체는 싸지만 origin→CDN egress, 지역별 가격 차이 등 누적될 수 있음. **hit ratio**를 KPI로 모니터링.

## 등장 사례

- ch01 — [[caching-strategies]] 직후 도입되어 web tier에서 정적 자산 서빙 부담을 제거. 이후 [[multi-data-center]] 구성에서도 글로벌 사용자 경험의 한 축.
