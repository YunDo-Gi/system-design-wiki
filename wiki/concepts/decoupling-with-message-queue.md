---
type: concept
tags: [architecture, async, decoupling]
sources: [ch01]
---

# 메시지 큐로 결합도 낮추기 (Decoupling with Message Queue)

## 한 줄 정의

producer가 메시지를 큐에 publish하고 consumer가 비동기로 consume함으로써 두 측을 시간적·공간적으로 분리하는 패턴 (ch01, p.34).

## 왜 필요한가

동기 호출 구조에서는 producer와 consumer가 **같이 살아 있어야** 작동한다. 둘 중 하나가 느리거나 죽으면 다른 한쪽도 영향 받는다. 또한 함께 묶여 있으면 독립적으로 스케일하기도 어렵다.

## 핵심 메커니즘

- **Producer/publisher**: 메시지를 만들어 큐에 publish.
- **Message queue**: 메모리·디스크에 메시지를 버퍼링하며 내구성(durability) 제공.
- **Consumer/subscriber**: 큐에서 메시지를 꺼내 정의된 동작 수행 (Figure 1-17).

책 예시 (ch01, p.34): 사진 처리 — web server가 작업을 큐에 publish, photo processing worker가 비동기로 처리. 큐가 길어지면 worker 추가, 비면 줄이는 식으로 **producer와 consumer가 독립 스케일**된다.

## 트레이드오프

- **장점**: 시간적 분리(consumer 다운에도 producer 동작), 부하 평탄화(buffer), 독립 스케일.
- **비용**: 추가 인프라(큐 자체의 가용성 관리), 처리 지연 증가, 메시지 중복·순서·정확히-한 번(exactly-once) 같은 분산 의미론 문제. 큐가 새 [[single-point-of-failure]]가 되지 않도록 이중화 필요.
- 동기 응답이 꼭 필요한 흐름엔 부적합.

## 등장 사례

- ch01 — [[multi-data-center]] 다음 단계. 시스템 컴포넌트를 더 잘게 쪼개 독립 확장하기 위해 도입. 이후 본격 큐 시스템([[message-queue]] 기술 페이지 참조)으로 구체화.
