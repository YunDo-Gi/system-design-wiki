---
type: concept
tags: [rate-limiting, algorithm]
sources: [ch04]
---

# 슬라이딩 윈도우 카운터 (Sliding Window Counter Algorithm)

## 한 줄 정의 / 동기

[[fixed-window-counter-algorithm]]과 [[sliding-window-log-algorithm]]의 **하이브리드**. 이전·현재 두 윈도우의 카운터만 유지하고 **현재 시각이 두 윈도우와 겹치는 비율로 가중 평균**해 롤링 윈도우의 요청 수를 근사한다 (ch04, p.65-66). 두 알고리즘의 약점을 양쪽에서 잘라낸 실용적 균형점.

Cloudflare 실측에서 4억 요청 중 **0.003% 만 잘못 허용/거절** — 대부분 실서비스에 충분한 정확도.

## 동작

```
window = 60s
limit = N

on request at time t:
    cur_key  = floor(t / window)
    prev_key = cur_key - 1
    offset = (t mod window) / window   # 현재 윈도우 내 진행 비율 (0~1)
    prev_weight = 1 - offset

    cur  = GET counter[cur_key]
    prev = GET counter[prev_key]
    rolling = cur + prev * prev_weight

    if rolling >= limit:
        drop(request)
    else:
        INCR counter[cur_key]
        EXPIRE counter[cur_key] (2 * window)
        forward(request)
```

이전 윈도우의 요청이 **균등 분포**라는 가정 하에 가중 평균으로 추정.

### 시각화

```
 prev minute             current minute
┌───────────────┬───────────────┐
│  prev count   │  cur count    │
│   = 5         │   = 3         │
└───────────────┴───────────────┘
           ↑ now (30% into current)
           ┌───────────────┐
           │ rolling window│ ← prev 70% + cur 30%
           └───────────────┘
   rolling = 3 + 5 × 0.7 = 6.5
```

### 책의 시각화 (Figure 4-11, 분당 7 요청)

- 이전 분 카운터: 5, 현재 분 카운터: 3.
- 새 요청이 현재 분의 **30% 지점**에 도착 → previous 윈도우와의 overlap = 70%.
- rolling = 3 + 5 × 0.7 = **6.5** → 반올림으로 6 또는 7.
- 6 ≤ 7 → 통과. 한 번 더 들어오면 한도 도달.

## 파라미터 · 튜닝 포인트

| 파라미터 | 의미 | 튜닝 방향 |
|---|---|---|
| `window` | 윈도우 길이 | 비즈니스 정책 |
| `limit` | 윈도우당 허용 카운트 | SLA |
| 반올림 정책 | floor / round / ceil | 약간 엄격하게(ceil) vs 관용(floor) |
| 데이터 | 카운터 2개 per key | TTL = 2 × window 로 자동 청소 |

이전 윈도우 분포가 매우 비균등(예: 시작 직후 몰린)이면 추정이 어긋날 수 있다. 단 Cloudflare 데이터처럼 평균적으로는 오차가 매우 작다.

## 트레이드오프

**Pros**
- 이전 윈도우 평균을 활용해 **버스트 평탄화**.
- **메모리 효율** — 윈도우당 카운터 2개만.
- 구현 비교적 단순. Redis Lua 한 스크립트로 충분.

**Cons**
- **근사** — 이전 윈도우 균등 분포 가정에 기반. 정확도 보장 못함.
- 엄밀한 한도가 필수인 도메인(보안·결제)엔 부적합 — 그 영역은 [[sliding-window-log-algorithm]].

## 다른 알고리즘과의 위치

| | 메모리 | 정확도 | 버스트 |
|---|---|---|---|
| [[fixed-window-counter-algorithm]] | 적음 | 낮음 | 경계 burst |
| [[sliding-window-log-algorithm]] | **많음** | **높음** | — |
| **Sliding window counter** | **적음** | 중·근사 | **평탄화** |
| [[token-bucket-algorithm]] | 적음 | 중 | 명시적 허용 |
| [[leaking-bucket-algorithm]] | 적음 | 중 | 큐로 흡수 |

산업의 기본 선택지로 자리잡은 알고리즘. **메모리 효율 + 경계 burst 회피**를 동시에 얻을 수 있다는 점이 매력.

## 실무 적용 시 고려사항

- **Redis Lua로 원자 실행**: GET prev/cur → 계산 → INCR을 한 스크립트에서. race condition 자연 해결.
- **`(2 × window)` TTL**: 이전 윈도우 카운터를 가중 평균에 쓰므로 만료가 너무 빠르면 0으로 잘못 계산.
- **사용자 안내**: 임계 직전에서는 결정이 **소수점 반올림에 좌우**되므로 보더라인 사용자가 "어제는 됐는데 오늘은 안 된다"고 느낄 수 있음 — retry-after 헤더로 명확히 안내.
- **모니터링**: 실측 통과율 vs 정책 한도를 비교해 오차를 측정. 오차가 크면(예: 5%) 이전 윈도우 분포가 매우 비균등 → log 방식으로 교체 고려.
- **분포 가정 점검**: 광고 캠페인 시작 직후, 새벽-아침 전환 시각 같은 **이상 분포 구간**에서 추정 오차가 커진다. 그런 시간대엔 정책을 보수적으로.

## 등장 사례

- ch04 — 다섯 번째이자 마지막 알고리즘. 산업 표준 선택지.
- **Cloudflare** — 4억 요청 실측에서 0.003% 오차로 채택 정당화 (책 reference [10]).
- 일반 공개 API에서 가장 흔히 채택되는 알고리즘.
