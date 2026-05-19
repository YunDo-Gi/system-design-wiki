---
type: concept
tags: [estimation, fundamentals, units]
sources: [ch02]
---

# 2의 거듭제곱 데이터 단위 (Power of Two Data Units)

## 한 줄 정의

분산 시스템 용량 계산의 기초 단위. 1바이트=8비트, ASCII 1자=1바이트, 그리고 2의 10승 단위로 KB→MB→GB→TB→PB 순으로 자릿수가 올라간다 (ch02, p.36).

## 왜 필요한가

데이터 양이 거대해지더라도 **자릿수 감각이 있어야** 추정에서 길을 잃지 않는다. 예: "5년 미디어 = 55PB"가 합리적인지 즉시 판단하려면 단위 환산이 머리에 있어야 한다.

## 핵심 메커니즘 — 환산표 (Table 2-1)

| Power | 근사값 | Full name | Short |
|---:|---|---|---|
| 2^10 | 1 Thousand | 1 Kilobyte | 1 KB |
| 2^20 | 1 Million | 1 Megabyte | 1 MB |
| 2^30 | 1 Billion | 1 Gigabyte | 1 GB |
| 2^40 | 1 Trillion | 1 Terabyte | 1 TB |
| 2^50 | 1 Quadrillion | 1 Petabyte | 1 PB |

이진(2^10=1024) vs 십진(10^3=1000) 구분은 면접에서는 보통 무시하고 근사. SI 표준에서 정확히 구분하려면 KiB/MiB/GiB(이진), KB/MB/GB(십진)로 나누지만, 책과 면접 관행은 이를 혼용한다.

## 트레이드오프 / 함정

- "5"라고만 적으면 5 KB인지 5 MB인지 모호 → 단위 라벨링 필수 ([[back-of-the-envelope-estimation]] 면접 팁).
- 네트워크 대역폭은 보통 **비트 단위** (Mbps = megabit/s)지만 스토리지는 **바이트 단위**다 — 8배 차이.

## 등장 사례

- ch02 — 추정의 가장 기초 도구. Twitter 예제의 미디어 스토리지(30TB/day, 55PB/5yr) 계산에 직접 사용.
