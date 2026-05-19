---
chapter: 3
title_en: A Framework for System Design Interviews
title_ko: 시스템 설계 면접 프레임워크
ingested_at: 2026-05-19
---

# A Framework for System Design Interviews

## 핵심 takeaway

- 시스템 설계 면접은 정답 맞히기가 아니라 **모호한 문제 위에서 동료처럼 협업하는 과정**을 보는 자리. 최종 설계보다 과정이 더 중요하다 (ch03, p.42).
- 효과적 진행을 위한 **4단계 프레임워크**: ① 문제 이해·범위 확정 → ② high-level 설계 + buy-in → ③ deep dive → ④ wrap up (ch03, p.43-53). → [[four-step-interview-framework]]
- 면접관이 보는 신호는 기술 외에도 **협업·압박 처리·모호함 해소·질문하는 능력**. 큰 red flag는 **과도설계(over-engineering)·완고함·시야 좁음** (ch03, p.42).
- **45분 시간 배분 가이드**: Step1 3-10분 / Step2 10-15분 / Step3 10-25분 / Step4 3-5분 (ch03, p.53).

## 본문 요약

장은 면접 자체를 어떻게 다룰지에 대한 메타 가이드다. 기술 컴포넌트가 아니라 **진행 절차**를 도입한다.

**Step 1 — 문제 이해·범위 확정 (3-10분)** (ch03, p.43-46)

빨리 답하지 말 것. 가정을 적고 면접관과 합의. 흔히 던지는 질문: 구체적 기능? 사용자 수? 3·6·12개월 후 스케일? 기술 스택? News feed 예제에서는 모바일/웹 여부, 핵심 기능, 정렬 기준, 친구 수 상한, DAU, 미디어 포함 여부를 묻는다.

**Step 2 — High-level 설계 + buy-in (10-15분)** (ch03, p.46-49)

박스 다이어그램으로 클라이언트·API·web server·DB·캐시·CDN·메시지 큐 등을 배치. **봉투 뒷면 추정으로 스케일이 맞는지** 확인 ([[back-of-the-envelope-estimation]]). 면접관과 use case를 함께 따라가며 edge case를 발굴. API 엔드포인트·DB 스키마를 이 단계에 넣을지는 문제 규모에 따라 다름 — "Design Google search"는 너무 저수준, "multi-player poker backend"는 적절.

**Step 3 — Deep dive (10-25분)** (ch03, p.49-51)

면접관과 함께 어떤 컴포넌트를 깊게 볼지 우선순위 매김. 시니어는 종종 성능 특성·병목·자원 추정. 시간 관리 핵심 — 사소한 디테일(예: Facebook EdgeRank 알고리즘)에 빠지지 말 것.

**Step 4 — Wrap up (3-5분)** (ch03, p.51-52)

- 병목·개선 여지 함께 짚기. "완벽"이라 말하지 말 것.
- 설계 요약(recap).
- 오류 케이스(서버 다운, 네트워크 손실).
- 운영 이슈(모니터링·롤아웃).
- 다음 스케일 곡선(1M → 10M 사용자) 대응.

**Dos / Don'ts** (ch03, p.52)

Dos: 항상 명료화 질문, 요구사항 이해, 여러 접근 제시, 핵심 컴포넌트부터, 면접관과 캐치볼, 포기 금지.
Don'ts: 준비 부족, 가정·요구 명료화 없이 솔루션, 한 컴포넌트에 너무 일찍 깊게, 막혔는데 침묵, 면접관이 끝났다 하기 전 끝났다 단정.

## 등장 개념

- [[four-step-interview-framework]] — 4단계 절차·시간 배분·Dos/Don'ts 통합 페이지
- [[back-of-the-envelope-estimation]] — Step 2에서 buy-in 위한 양적 검증 도구

## 등장 기술

(새로 도입된 기술 컴포넌트는 없음. News Feed 예제에 등장한 Post Service / Fanout Service / Notification Service / Graph DB / News Feed Cache 등은 ch11에서 본격 다룸.)

## 면접 관점 메모

- 1·2장이 "재료"였다면 3장은 "조리법". 본 챕터의 4단계는 이후 ch04~ch16의 모든 설계 문제에서 동일하게 적용된다.
- 책 본문에 나오는 News Feed 예제 다이어그램(Figure 3-1 ~ 3-4)은 ch01에서 만든 어휘들의 종합 활용 예 — [[load-balancer]] / [[dns]] / [[cdn]] / [[caching-strategies]] / [[decoupling-with-message-queue]] / 인증·rate limiting이 한 그림에 모인다.
- 면접에서 자주 새는 시간: Step1 질문 부족 / Step3에서 한 컴포넌트에 빠짐. 시계 의식적으로 보기.
