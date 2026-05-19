---
type: concept
tags: [rate-limiting, algorithm]
sources: [ch04]
---

# 고정 윈도우 카운터 (Fixed Window Counter Algorithm)

## 한 줄 정의 / 동기

시간 축을 고정 길이 구간(window)으로 분할하고 각 구간에 카운터를 두어 임계치 도달 시 차단하는 가장 단순한 처리율 제한 알고리즘 (ch04, p.62-63). 구현이 짧고 메모리가 거의 안 들어 "1분에 N개 허용" 같은 인간 친화적 정책에 잘 맞는다.

## 동작

```
window_size = 60s      # 예: 1분
limit = N

on request at time t:
    window_key = floor(t / window_size)
    count = INCR counter[window_key]
    EXPIRE counter[window_key] window_size  # TTL로 자동 청소
    if count > limit:
        drop(request)
    else:
        forward(request)
```

[[redis]]의 `INCR` + `EXPIRE` 조합으로 한 명령씩 원자 실행 가능. window_key를 매분 갱신해 자연스럽게 새 카운터로 넘어간다.

## 파라미터 · 튜닝 포인트

| 파라미터 | 의미 | 튜닝 방향 |
|---|---|---|
| `window_size` | 분할 시간 단위 | 사용자가 이해하기 쉬운 단위(분·시간·일) |
| `limit` | 윈도우당 허용 요청 수 | 비즈니스 SLA |

## 치명적 단점 — 경계 burst

윈도우 **경계에서 임계치의 2배가 통과**할 수 있다 (Figure 4-9).

**책 예시** (분당 5 요청 허용):

- `2:00:30~2:01:00` 사이에 5개 요청 → 통과.
- `2:01:00~2:01:30` 사이에 5개 요청 → 통과.
- 각 윈도우는 임계치 내지만, **임의의 1분 롤링 윈도우 `2:00:30~2:01:30` 기준으로는 10개** = 허용치의 2배.

flash sale·캠페인 시작 시각 직후 같은 burst를 막지 못한다 → [[sliding-window-log-algorithm]]·[[sliding-window-counter-algorithm]]의 등장 동기.

## 트레이드오프

**Pros**
- 구현·이해 가장 쉬움.
- 메모리 거의 무료 (윈도우당 카운터 1개).
- "오전 9시에 한도 리셋" 같은 정책에 자연스러움.

**Cons**
- **경계 burst로 최대 2배 트래픽 누수**.
- 정책 의미가 "어떤 1분이든 5개 이하"가 아니라 "고정된 분당 5개"라는 점을 사용자에게 명확히 설명해야 함.

## 다른 알고리즘과의 위치

| 알고리즘 | 정확도 | 메모리 | 비고 |
|---|---|---|---|
| **Fixed window counter** | 낮음 | **적음** | 경계 burst |
| [[sliding-window-log-algorithm]] | **높음** | 많음 | 정확하지만 비쌈 |
| [[sliding-window-counter-algorithm]] | 중·근사 | 적음 | 두 약점을 균형 |

[[token-bucket-algorithm]]·[[leaking-bucket-algorithm]]은 결이 다른 카운터(토큰/큐) 방식.

## 실무 적용 시 고려사항

- **경계 burst 허용 가능 여부**를 미리 판단. 광고·검색 같은 트래픽엔 무난하지만, **결제·로그인** 같은 보안 민감 엔드포인트엔 위험. 보안용이면 sliding 계열로.
- **클럭 동기화**: 윈도우 시작 시각이 노드 간 어긋나면 정책 일관성이 깨짐 → NTP·UTC 통일.
- **TTL 활용**: `EXPIRE`를 통해 만료된 카운터 자동 청소 — DB에 카운터를 저장하지 말고 in-memory TTL 사용.
- **윈도우 시작 정책**: 자정 기준 / 사용자 가입 시각 기준 등에 따라 사용자 경험이 달라짐. 결정을 명시적으로.

## 등장 사례

- ch04 — 세 번째 알고리즘. 단점을 드러내며 sliding window 계열로 자연스럽게 넘어가는 디딤돌 역할.
- 단순 API quota 시스템 (예: "월 1000회 호출")에서 흔히 사용 — 경계 burst가 month 단위에서는 거의 무해.
