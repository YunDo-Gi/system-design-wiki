---
type: tech
category: cdn
sources: [ch01]
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

## 전형적 사용 사례

- 정적 자산 글로벌 배포 (책에서 주로 다루는 범위).
- 동적 콘텐츠 캐싱(쿠키·쿼리·경로 기반)도 가능하지만 본 책 범위 밖.

## 등장 사례

- ch01 — [[caching-strategies]] 직후 도입되어 web tier에서 정적 자산 서빙 부담을 제거. 이후 [[multi-data-center]] 구성에서도 글로벌 사용자 경험의 한 축.
