---
type: tech
category: queue
sources: [ch01, ch10, ch11, ch12, ch14]
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

## 언제 선택하는가 / 대안 비교

| 제품 | 모델 | 특성 | 적합 |
|---|---|---|---|
| **Kafka** | 분산 로그, partition·offset | 매우 높은 처리량, 메시지 보관 | 이벤트 스트리밍, log aggregation, CDC |
| **RabbitMQ** | 큐·exchange·바인딩 | 라우팅 유연, 트랜잭션 | 작업 큐, 복잡한 라우팅 |
| **AWS SQS** | 매니지드 큐 | 운영 부담 0, exactly-once는 FIFO만 | 클라우드 네이티브 |
| **Redis Streams** | 가벼운 스트림 | 빠른 in-memory | 캐시 인접 워크로드 |
| **NATS / JetStream** | 가벼운 pub/sub | 저지연, 단순 | 마이크로서비스 내부 |

**선택 기준**:
- 메시지 **보관**·재생 필요 → Kafka, JetStream.
- **작업 큐** 패턴, 라우팅·재시도 정책이 핵심 → RabbitMQ, SQS.
- 매니지드를 원함 → SQS, Pub/Sub.

## 전형적 사용 사례

- 무거운 백그라운드 작업(사진 처리·이메일 발송·트랜스코딩) — 책의 photo customization 예시 (ch01, p.34, Figure 1-18).
- 스파이크 트래픽 흡수(부하 평탄화).
- 서비스 간 이벤트 기반 통합.
- 데이터 파이프라인·CDC.

## 실무 함정

- **At-least-once의 의미를 무겁게**: 거의 모든 큐는 메시지를 두 번 이상 줄 수 있음. consumer가 **idempotent**해야 한다 (자세한 패턴은 [[decoupling-with-message-queue]]).
- **순서 보장의 비용**: 글로벌 순서는 거의 항상 처리량을 죽임. **partition 단위 순서**가 표준. 같은 entity는 같은 partition key로.
- **DLQ 운영 누락**: DLQ를 만들기만 하고 모니터링 안 하면 조용히 데이터가 쌓이고 시스템이 망가짐. alert·복구 절차를 처음부터 함께.
- **Consumer lag**: 큐 길이만 보면 안 됨. **oldest message age** = 사용자 대기 시간. 그게 SLA 지표.
- **Backpressure 부재**: producer가 무제한 publish하면 큐가 디스크·메모리를 다 먹음. broker 측 quota 또는 producer 측 throttle 필요.
- **메시지 크기 함정**: 일반적으로 1MB 이상 메시지는 비효율. 큰 페이로드는 S3 등에 두고 큐엔 **참조(URL/ID)** 만.
- **스키마 호환성**: 메시지 포맷을 바꿀 때 forward/backward compatibility 깨지면 consumer 무한 실패. **schema registry** (Confluent, Apicurio) 도입.
- **트랜잭션 outbox 패턴**: DB write와 메시지 publish가 한 트랜잭션이 아니므로 둘 사이 불일치 가능. **outbox 테이블** + CDC 패턴이 표준 해법.
- **재시도 폭주**: 실패한 메시지를 즉시 재시도하면 downstream 폭주. **exponential backoff + jitter**.

## 등장 사례

- ch01 — [[multi-data-center]] 다음 단계로 도입. 시스템 컴포넌트를 더 잘게 쪼개 독립 확장하기 위한 표준 도구로 제시됨.
