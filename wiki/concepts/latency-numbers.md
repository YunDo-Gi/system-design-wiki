---
type: concept
tags: [performance, latency, fundamentals]
sources: [ch02]
---

# 프로그래머가 알아야 할 지연 시간 (Latency Numbers Every Programmer Should Know)

## 한 줄 정의

Google의 Jeff Dean이 정리한, 컴퓨터 기본 연산들의 전형적 소요 시간 표. 시스템 설계 추정의 핵심 기준 (ch02, p.37).

## 왜 필요한가

"이 캐시 hit가 의미가 있나?", "DC 간 호출을 해도 되나?" 같은 결정을 **자릿수 단위로 즉답**하려면 표준 지연 수치가 머리에 있어야 한다.

## 핵심 메커니즘 — Dean의 표 (Table 2-2, 2010 기준)

| Operation | Time |
|---|---|
| L1 cache reference | 0.5 ns |
| Branch mispredict | 5 ns |
| L2 cache reference | 7 ns |
| Mutex lock/unlock | 100 ns |
| Main memory reference | 100 ns |
| Compress 1KB with Zippy | 10 µs |
| Send 2KB over 1 Gbps network | 20 µs |
| Read 1 MB sequentially from memory | 250 µs |
| Round trip within same DC | 500 µs |
| Disk seek | 10 ms |
| Read 1 MB sequentially from network | 10 ms |
| Read 1 MB sequentially from disk | 30 ms |
| Send packet CA → Netherlands → CA | 150 ms |

2020년 갱신본(Figure 2-1)은 일부 수치가 개선되었으나(예: memory 1MB 순차 3µs, SSD seek 16µs, disk seek 2ms, disk 1MB 순차 825µs) **상대적 비율은 거의 동일**하다.

## 책이 도출하는 5가지 결론 (ch02, p.39)

1. 메모리는 빠르고 디스크는 느리다.
2. 가능하면 disk seek를 피한다 (순차 접근 > 랜덤 접근).
3. 단순 압축 알고리즘은 빠르다 — 사실상 공짜.
4. 인터넷 전송 전 압축하라.
5. 데이터센터들은 보통 다른 리전에 있고, DC 간 데이터 전송은 비싸다 → [[multi-data-center]] 설계 시 동기 호출 최소화.

## 트레이드오프 / 활용

- **자릿수 비교**가 핵심: L1 ≈ 1ns, 메모리 ≈ 100ns, DC 내 RTT ≈ 500µs, 디스크 seek ≈ 10ms, 대륙 간 RTT ≈ 150ms. 약 **3자릿수씩 단계가 벌어진다**.
- 수치는 시간이 지나면서 빨라지지만 **상대 비율은 유지** — 메모리 vs 디스크 차이는 여전히 크다.

## 실무 적용 시 고려사항

- **캐시 hit 가치 계산**: 메모리 hit 100ns vs DB query 1ms = 만 배 차이. 캐시 hit ratio 90%면 평균 응답이 어떻게 바뀌는지 즉석 계산 가능.
- **DC 간 동기 호출 회피**: 한 요청 처리에 다른 리전 호출이 1번이라도 들어가면 150ms 추가 → 사용자가 느낄 정도. 비동기·복제 전략으로 회피.
- **마이크로서비스 분해 비용**: 한 호출을 10개 RPC로 쪼개면 DC 내 RTT만으로도 5ms 추가. 너무 잘게 쪼개면 누적 지연 비싸다.
- **압축이 거의 공짜인 이유의 응용**: HTTP gzip·DB column 압축·로그 압축 모두 거의 무료. 대역폭·스토리지 절감 효과는 명확.
- **Disk seek 회피 → 순차 IO 우선**: 로그 구조 저장소(LSM tree, Kafka)가 빠른 이유. 랜덤 IO에 의존하는 설계는 피한다.
- **응답 시간 예산(latency budget)**: 사용자가 느끼는 200ms 안에서 각 컴포넌트가 얼마를 쓸 수 있는지 미리 분배. DB 50ms, 캐시 1ms, 네트워크 20ms, 비즈니스 로직 100ms 식.
- **꼬리 지연(tail latency)**: 평균은 의미 약함. p95/p99/p99.9에 주목. 자릿수가 평균과 다른 경우 흔함 — fan-out 시 한 컴포넌트 꼬리가 전체를 결정.

## 등장 사례

- ch02 — 봉투 뒷면 추정의 두 번째 기둥.
- [[caching-strategies]], [[cdn]], [[multi-data-center]]의 정성적 결론은 모두 본 표의 자릿수 차이에 뿌리를 둔다.
- 참고: Colin Scott의 interactive latency 페이지 (책 reference [3]).
