---
type: concept
tags: [scalability, fundamentals]
sources: [ch01]
---

# 수직 vs 수평 확장 (Vertical vs Horizontal Scaling)

## 한 줄 정의

**Vertical scaling (scale up)** 은 한 서버의 자원(CPU/RAM/Disk)을 키우는 것, **Horizontal scaling (scale out)** 은 서버 대수를 늘리는 것이다 (ch01, p.18).

## 왜 필요한가

저트래픽 환경에서는 vertical이 단순해서 좋다. 그러나 사용자가 늘면 단일 서버는 세 가지 한계에 부딪힌다 (ch01, p.18).

1. **하드웨어 상한**: CPU·메모리를 무한히 추가할 수 없다.
2. **failover·redundancy 부재**: 한 대가 죽으면 서비스 전체가 죽는다 — 전형적 [[single-point-of-failure]].
3. **비용**: 고성능 단일 머신은 가격이 비선형으로 비싸진다.

수평 확장은 이 세 문제를 한꺼번에 풀지만 — **상태 관리, 트래픽 분산, 데이터 일관성** 같은 새로운 분산 문제를 부른다.

## 핵심 메커니즘

- **앞단**: [[load-balancer]]가 트래픽을 여러 서버로 분배. 한 서버 다운 시 자동 우회.
- **web tier**: [[stateless-web-tier]]로 만들어야 임의 서버로 라우팅 가능. 세션은 공유 저장소에 둔다.
- **data tier**: 우선 [[database-replication]] (읽기 분산), 그 다음 [[sharding]] (쓰기·저장 용량 분산).

## 트레이드오프

| 측면 | Vertical | Horizontal |
|---|---|---|
| 구현 단순성 | 높음 | 낮음 (분산 이슈) |
| 한계 | 하드웨어 상한 | 사실상 없음 |
| 가용성 | SPOF | 이중화 가능 |
| 운영 비용 곡선 | 가파름 | 완만 |
| 데이터 일관성 | 자명 | 신경 써야 함 |

대규모 시스템은 결국 horizontal로 가지만, 초기 단계나 OLTP DB master 같은 일부 영역에선 vertical이 여전히 합리적이다 (Stack Overflow가 2013년 단일 master DB 한 대로 1천만 MAU를 처리한 사례, ch01, p.35).

## 실무 적용 시 고려사항

- **전환 시점 판단**: vertical의 한계는 단일 지표가 아니라 CPU/메모리/디스크 IO/네트워크/응답 지연 p95~p99 가운데 **무엇이 먼저 saturation에 도달했는가**로 판단. 미리 horizontal로 가면 운영 복잡도가 비용 대비 안 맞는 경우가 흔하다.
- **모든 tier가 동시에 horizontal일 필요는 없다**: web tier는 일찍 horizontal로, OLTP DB master는 vertical을 길게 — 흔한 조합. DB는 [[database-replication]]·[[sharding]] 도입이 운영 비용을 크게 키운다.
- **가짜 horizontal scale 함정**: web tier를 [[stateless-web-tier]]로 만들지 않은 채 서버만 늘리면 sticky session·세션 손실로 더 큰 문제를 만든다. 상태 외부화가 선결 조건.
- **클라우드 환경의 hybrid 접근**: 오토스케일링은 horizontal이지만, 각 인스턴스 자체를 vertical로 키우는(예: m5.large → m5.2xlarge) 결정도 함께 함. 두 축을 모두 만진다.
- **비용 모델링**: vertical은 하드웨어 가격이 비선형 증가, horizontal은 운영·네트워크·라이선스 등 운영 비용이 누적. 손익분기점을 비용 데이터로 확인.

## 등장 사례

- ch01 — 단일 서버 → load balancer + replication → cache/CDN → 무상태 + multi-DC → 큐 + 샤딩으로 이어지는 점진적 horizontal 확장 서사의 출발점.
- Stack Overflow — 2013년 단일 master DB 1대로 월 1천만 MAU 처리. vertical이 합리적이었던 사례 (ch01 p.35).
