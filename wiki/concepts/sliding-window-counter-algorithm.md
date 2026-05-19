---
type: concept
tags: [rate-limiting, algorithm]
sources: [ch04]
---

# 슬라이딩 윈도우 카운터 (Sliding Window Counter Algorithm)

## 한 줄 정의

[[fixed-window-counter-algorithm]]과 [[sliding-window-log-algorithm]]의 **하이브리드**. 이전 윈도우와 현재 윈도우의 카운터를 보유하고 **롤링 윈도우의 요청 수를 가중 합산으로 근사**한다 (ch04, p.65-66).

## 왜 필요한가

- fixed window의 메모리 효율 ✓
- sliding window log의 경계 burst 회피 ✓ (단, 근사)

Cloudflare 실측에서 4억 요청 중 **0.003% 만 잘못 허용/거절** — 실용적으로 충분히 정확 (ch04, p.66).

## 핵심 메커니즘

이전·현재 두 윈도우의 카운터만 유지하고, 현재 시각이 윈도우의 어느 지점인지에 따라 **선형 보간**.

```
rolling_count = current_window_count
              + previous_window_count × overlap_percentage_of_previous_window
```

### 책 예시 (Figure 4-11, 분당 7 요청 허용)

- previous 분 카운터: 5, current 분 카운터: 3.
- 새 요청이 current 윈도우의 **30% 지점**에 도착 → previous 윈도우와의 overlap = 70%.
- rolling = 3 + 5 × 0.7 = 6.5 → 반올림 후 6 (또는 6.5).
- 6 ≤ 7 → 통과. 다음 1개부터 차단.

## 트레이드오프

**Pros**
- 이전 윈도우 평균을 활용해 **버스트를 평탄화**.
- **메모리 효율** (윈도우당 카운터 2개만).

**Cons**
- 이전 윈도우의 요청이 **균등 분포**라는 가정에 기반한 **근사**. 엄밀한 한도가 필요한 경우엔 부적합.
- 그러나 Cloudflare 실측 오차가 매우 낮아 대부분의 실서비스에 충분.

## 다른 알고리즘과의 위치

| | 메모리 | 정확도 | 버스트 |
|---|---|---|---|
| Fixed window counter | 적음 | 낮음 (경계 burst) | — |
| Sliding window log | **많음** | 높음 | — |
| **Sliding window counter** | **적음** | 중·근사 | 평탄화 |

## 등장 사례

- ch04 — 다섯 번째이자 마지막 알고리즘. 메모리·정확도의 균형으로 산업에서 인기.
- Cloudflare가 실측 데이터로 정확도를 입증한 사례로 언급.
