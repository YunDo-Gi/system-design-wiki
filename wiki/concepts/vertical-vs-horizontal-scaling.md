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

## 등장 사례

- ch01 — 단일 서버 → load balancer + replication → cache/CDN → 무상태 + multi-DC → 큐 + 샤딩으로 이어지는 점진적 horizontal 확장 서사의 출발점.
