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

## SLA · SLO · SLI · Error Budget

가용성을 운영하는 SRE 어휘 (Google SRE book에서 정착):

- **SLI** (Service Level Indicator): 측정 가능한 지표. 예: 5xx 비율, 응답 지연 p99.
- **SLO** (Service Level Objective): 내부 목표치. 예: "5xx 비율 ≤ 0.1%".
- **SLA** (Service Level Agreement): 외부 약속. 보통 SLO보다 보수적으로 설정. 위반 시 보상.
- **Error budget**: 1 - SLO. "허용된 다운타임 잔량". 소진하면 새 기능 출시 중단, 안정화 우선.

이 4개 어휘로 가용성을 정량 운영함. 책은 SLA만 다루지만 실무에선 4개 모두 사용.

## 실무 적용 시 고려사항

- **현실적 목표 설정**: 5 nines(연 5분 다운)는 매우 비싸다. 대부분 서비스는 3~4 nines가 합리적. 사용자 가치에 비례한 투자 결정.
- **의존성 가용성 합산**: 인증·결제·외부 API 등 의존성을 곱하면 자기 SLA 상한이 결정됨. 의존성 SLA 합쳐서 자기 SLA 제시.
- **계획 점검 포함 여부 명시**: "scheduled maintenance excluded"인지 명시. 사용자 입장에선 점검 다운도 다운.
- **측정 윈도우**: 월 단위 vs 분기 vs 연 단위에 따라 짧은 사고의 영향도가 다름. 짧을수록 엄격.
- **사용자 관점 측정**: 서버 ping이 아니라 **사용자 흐름 성공률** (synthetic monitoring·RUM)로 측정해야 의미 있음.
- **Error budget 운영**: budget 잔량을 팀 KPI로. 빠르게 소진되면 출시 속도 조정. 남으면 더 공격적 출시 가능.
- **장애 등급 분류**: 가용성 영향이 큰 사고(P1)와 부분 기능 저하(P2)를 분리해 SLI 정의. "다운"의 정의를 명확히.
- **Multi-region 가용성 계산**: 두 리전 active-active면 1 - (1-p)² ≈ 2p (p = 단일 region 실패율). 4 nines 컴포넌트 둘이면 7 nines급 가능.

## 등장 사례

- ch02 — 추정 기초 수치 중 하나로 도입.
- [[database-replication]], [[multi-data-center]], [[single-point-of-failure]]의 모든 가용성 향상 패턴은 결국 nines를 더 보태기 위한 수단.
- Google·Amazon·Microsoft 클라우드 — 99.9~99.99% SLA 공개.
