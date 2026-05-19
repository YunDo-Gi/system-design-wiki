---
type: tech
category: queue
sources: [ch01]
---

# 메시지 큐 (Message Queue)

## 한 줄 정의

producer가 publish한 메시지를 내구성 있게 보관하고 consumer가 비동기로 가져가도록 해주는 미들웨어 컴포넌트 (ch01, p.34).

## 주요 특성

- **비동기 처리·버퍼링**: producer/consumer가 동시에 살아 있지 않아도 됨.
- **결합도 분리**: 두 측이 큐 인터페이스만 공유 → 독립 배포·독립 스케일 ([[decoupling-with-message-queue]]).
- **내구성**: 메시지를 메모리·디스크에 보존.
- 운영 시 고려: 순서 보장, 중복 처리(at-least-once vs exactly-once), DLQ(dead-letter queue), 큐 자체의 [[single-point-of-failure]] 회피(클러스터링).

대표 제품(책 본문에 명시 없음, 일반 지식): Kafka, RabbitMQ, AWS SQS, Google Pub/Sub.

## 전형적 사용 사례

- 무거운 백그라운드 작업(사진 처리·이메일 발송·트랜스코딩) — 책의 photo customization 예시 (ch01, p.34, Figure 1-18).
- 스파이크 트래픽 흡수(부하 평탄화).
- 서비스 간 이벤트 기반 통합.

## 등장 사례

- ch01 — [[multi-data-center]] 다음 단계로 도입. 시스템 컴포넌트를 더 잘게 쪼개 독립 확장하기 위한 표준 도구로 제시됨.
