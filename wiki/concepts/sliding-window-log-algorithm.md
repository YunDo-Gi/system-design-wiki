---
type: concept
tags: [rate-limiting, algorithm]
sources: [ch04]
---

# 슬라이딩 윈도우 로그 (Sliding Window Log Algorithm)

## 한 줄 정의 / 동기

요청 **타임스탬프를 모두 저장**하고, 매 요청마다 현재 윈도우 밖의 오래된 타임스탬프를 제거해 정확한 윈도우 내 요청 수를 유지하는 처리율 제한 알고리즘 (ch04, p.64-65). [[fixed-window-counter-algorithm]]의 경계 burst를 **완벽하게** 제거한다 — 어떤 1분 롤링 윈도우든 임계치 초과 불가.

## 동작

[[redis]]의 **sorted set**이 자연스러운 자료구조. timestamp를 score 겸 member로 저장하면 윈도우 밖 일괄 제거가 한 명령으로 끝난다.

```
key = "rate:{user}"
window = 60s
limit = N

on request at time t:
    # 1. 윈도우 밖 제거
    ZREMRANGEBYSCORE key 0 (t - window)
    # 2. 현재 카운트
    count = ZCARD key
    if count >= limit:
        reject(request)        # 단, ZADD는 여전히 수행할 수도 있음 (책 정의)
    else:
        ZADD key t t
        EXPIRE key window
        forward(request)
```

### 책의 시각화 (Figure 4-10, 분당 2 요청)

| 시각 | 로그 (윈도우 청소 후) | 결정 |
|---|---|---|
| 1:00:01 | `[1:00:01]` size 1 ≤ 2 | 통과 |
| 1:00:30 | `[1:00:01, 1:00:30]` size 2 ≤ 2 | 통과 |
| 1:00:50 | `[1:00:01, 1:00:30, 1:00:50]` size 3 > 2 | **reject** (그래도 로그에 남음) |
| 1:01:40 | 1:00:40 이전 두 개 제거 → `[1:00:50, 1:01:40]` size 2 ≤ 2 | 통과 |

## 파라미터 · 튜닝 포인트

| 파라미터 | 의미 | 튜닝 방향 |
|---|---|---|
| `window` | 롤링 윈도우 길이 | 비즈니스 정책 |
| `limit` | 윈도우당 허용 카운트 | SLA |
| 로그 저장소 | sorted set per key | TTL로 자동 청소 |

## 트레이드오프

**Pros**
- **매우 정확**. 어떤 롤링 윈도우에서도 임계치 초과 없음.
- 보안·정합성 민감 엔드포인트(로그인·결제)에 적합.

**Cons**
- **메모리 비용 큼**. rejected 요청 타임스탬프도 일정 시간 잔존. 트래픽 N RPS·윈도우 W초면 메모리는 O(N × W).
- 매 요청마다 sorted set 조작 → CPU·네트워크 비용 ↑.
- 윈도우가 길고 트래픽이 많을수록 비용 증가가 가파르다.

## 다른 알고리즘과의 위치

| 알고리즘 | 정확도 | 메모리 | 적합한 상황 |
|---|---|---|---|
| [[fixed-window-counter-algorithm]] | 낮음 | 적음 | 단순·관용 |
| **Sliding window log** | **높음** | **많음** | 엄격·보안 |
| [[sliding-window-counter-algorithm]] | 중·근사 | 적음 | 일반 API (Cloudflare) |

비용 vs 정확도의 양 극단. 대부분의 실서비스는 sliding window counter로 충분하지만, **엄격함이 필요한 곳에선 이 알고리즘이 유일한 선택**.

## 실무 적용 시 고려사항

- **분산 환경**: [[redis]] sorted set을 중앙에 두면 race condition은 ZADD·ZREMRANGEBYSCORE의 원자성으로 자연 해결.
- **메모리 추정**: timestamp 8B + score 8B + 오버헤드 → 한 요청당 ~50B (sorted set entry). 1000 RPS · 1분 = 60,000 entries × 50B = 3MB/key. 사용자 1M이면 3TB.
- **샤딩**: 사용자별 key를 Redis Cluster slot에 분산. hot key(예: 일부 셀럽)는 추가 분할 필요.
- **TTL 안전망**: 명시적 EXPIRE를 매번 갱신해 dead key 누적 방지.
- **대안 고려**: 메모리 부담이 비즈니스 비용을 넘으면 [[sliding-window-counter-algorithm]]으로 다운그레이드.

## 등장 사례

- ch04 — 네 번째 알고리즘. fixed window의 결함을 정확히 해결하는 모델로 등장.
- [[redis]] sorted set이 sliding window log를 거의 그대로 받아주는 데이터 구조라는 점이 책에서도 강조됨.
- 보안·금융 영역의 로그인 시도·결제 호출 제한에 자주 채택.
