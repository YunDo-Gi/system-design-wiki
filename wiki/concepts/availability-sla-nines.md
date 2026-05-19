---
type: concept
tags: [availability, sla, reliability]
sources: [ch02]
---

# 가용성과 SLA Nines (Availability SLA Nines)

## 한 줄 정의

시스템이 정상 동작한 비율을 백분율로 나타낸 지표. 99%, 99.9%, ... 형태로 표기하며 **9의 개수(nines)** 가 많을수록 좋다 (ch02, p.40).

## 왜 필요한가

가용성은 **확률·시간으로 환산되는 정량 목표**다. "고가용성"이라는 모호한 표현 대신 SLA로 "연간 다운타임 N분 이하"를 약속하면 설계·예산·이중화 수준을 정량적으로 결정할 수 있다.

## 핵심 메커니즘

- **SLA (Service Level Agreement)**: 제공자와 고객 사이의 가동률 약속. 위반 시 환불·크레딧 같은 보상이 따라붙는다.
- 대형 클라우드(Amazon, Google, Microsoft Compute)는 보통 **99.9% 이상**에서 시작 (ch02, p.40).
- 가용성은 일반적으로 **나인의 개수**로 말한다 — "three nines", "four nines".

### 다운타임 환산표 (Table 2-3)

| Availability | Downtime/day | Downtime/year |
|---|---|---|
| 99% | 14.40 min | 3.65 days |
| 99.9% | 1.44 min | 8.77 hours |
| 99.99% | 8.64 sec | 52.60 min |
| 99.999% | 864 ms | 5.26 min |
| 99.9999% | 86.4 ms | 31.56 sec |

## 트레이드오프 / 함정

- **나인 하나 추가의 비용은 보통 자릿수 단위로 증가**. 5 nines를 약속하려면 전 구간 이중화·자동 페일오버·카오스 테스트 같은 투자가 필요하다.
- **컴포넌트 가용성은 곱해진다**: 99.9% 컴포넌트 3개를 직렬 의존하면 전체 ≈ 99.7%. 그래서 [[single-point-of-failure]] 제거와 직렬 의존성 축소가 중요.
- 측정 단위가 **연 단위인지 월 단위인지**, 계획된 점검(planned downtime)을 포함하는지에 따라 같은 숫자도 의미가 달라진다.

## 등장 사례

- ch02 — 추정 기초 수치 중 하나로 도입.
- [[database-replication]], [[multi-data-center]], [[single-point-of-failure]]의 모든 가용성 향상 패턴은 결국 nines를 더 보태기 위한 수단.
