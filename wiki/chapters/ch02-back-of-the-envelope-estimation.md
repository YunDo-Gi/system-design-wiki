---
chapter: 2
title_en: Back-of-the-Envelope Estimation
title_ko: 봉투 뒷면 추정
ingested_at: 2026-05-19
---

# Back-of-the-Envelope Estimation

## 핵심 takeaway

- 봉투 뒷면 추정은 **사고 실험 + 표준 성능 수치 조합으로 설계 후보의 적합성을 빠르게 판단**하는 기법. Jeff Dean의 정의를 인용한다 (ch02, p.35).
- **세 가지 기초 수치를 외워둬야 한다**: 2의 거듭제곱 데이터 단위, 프로그래머가 알아야 할 지연 시간, 가용성 nines (ch02, p.35).
- **정답이 아닌 과정이 평가 대상**: 반올림·근사·가정 명시·단위 명시·연습이 면접에서의 4대 팁 (ch02, p.42).
- **자주 묻는 추정 항목**: QPS, peak QPS, 스토리지, 캐시 크기, 서버 수 (ch02, p.42).

## 본문 요약

장은 면접에서 시스템 용량·성능 요구사항을 빠르게 추정하는 **공통 어휘**를 정리한다.

**1) 2의 거듭제곱 (Power of 2)** — [[power-of-two-data-units]] (ch02, p.36).

분산 시스템의 데이터 양은 거대해질 수 있지만 계산은 결국 기본기로 환원된다. 1바이트 = 8비트, ASCII 1자 = 1바이트. 2^10≈천(KB), 2^20≈백만(MB), 2^30≈십억(GB), 2^40≈조(TB), 2^50≈천조(PB).

**2) 지연 시간 (Latency numbers)** — [[latency-numbers]] (ch02, p.37-39).

Jeff Dean(2010)의 표와 2020년 갱신본을 제시. 표에서 얻는 5가지 결론:

- 메모리는 빠르고 디스크는 느리다.
- 가능하면 disk seek를 피한다.
- 단순 압축 알고리즘은 빠르다.
- 인터넷 전송 전 압축하라.
- 데이터센터들은 보통 다른 리전에 있고, DC 간 데이터 전송에 시간이 걸린다 — [[multi-data-center]] 설계와 직결.

**3) 가용성 (Availability numbers)** — [[availability-sla-nines]] (ch02, p.40).

100%는 무중단을 의미하며 대부분 서비스는 99~100% 사이. **SLA**(Service Level Agreement)는 제공자가 약속하는 가동률. 대형 클라우드(Amazon/Google/Microsoft)는 99.9% 이상에서 시작. nines가 많아질수록 좋다 (99%=연 3.65일 다운 → 99.9999%=연 31.56초 다운).

**4) 예제: Twitter QPS와 스토리지 추정** (ch02, p.41) — [[back-of-the-envelope-estimation]]의 페이지 본문에 상세 작업 흐름을 옮겨둔다.

- 가정: 3억 MAU, 50% DAU, 1인당 2 트윗/일, 트윗 10%에 미디어, 5년 보관.
- QPS = 1.5억 × 2 ÷ 86400 ≈ **3,500**. peak QPS = 2× ≈ **7,000**.
- 미디어 스토리지 = 1.5억 × 2 × 10% × 1MB = **30TB/day** → 5년 ≈ **55PB**.

**5) 팁 (Tips)** — [[back-of-the-envelope-estimation]]의 면접 팁 절 참조 (ch02, p.42).

- 반올림·근사로 단순화 (99987/9.1 → 100000/10).
- 가정을 적어두고 나중에 다시 참조.
- 단위 라벨링 (5 → "5 MB"로).
- QPS·peak QPS·스토리지·캐시·서버 수 등 흔한 추정 항목을 미리 연습.

## 등장 개념

- [[back-of-the-envelope-estimation]] — 장 전체 주제·Twitter 예제·면접 팁 모음
- [[power-of-two-data-units]] — KB/MB/GB/TB/PB 환산
- [[latency-numbers]] — Jeff Dean의 표, 결론 5가지
- [[availability-sla-nines]] — 가동률 ↔ 다운타임, SLA

## 등장 기술

(이 장에서 새로 도입된 기술 컴포넌트는 없음 — 양적 사고 도구만 다룸.)

## 면접 관점 메모

- 면접에서 추정은 거의 매번 등장. **숫자 자체보다 가정을 큰 소리로 말하고, 단위를 적고, 단순화하는 모습**을 보여야 한다.
- 5가지 항목은 외워두면 좋음: 데이터 단위 표, latency 표, nines 표, peak QPS 관행(2×), 1년=3600×24×365 ≈ 3.15×10^7초.
- 후속 장과의 연결: [[multi-data-center]]의 DC 간 지연 비용, [[caching-strategies]]의 캐시 hit/miss 비용, [[sharding]]의 데이터 양 분할 판단 모두 본 장 수치를 근거로 한다.
