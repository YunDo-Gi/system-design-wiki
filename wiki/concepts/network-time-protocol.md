---
type: concept
tags: [distributed-systems, time]
sources: [ch04, ch07]
---

# Network Time Protocol (NTP)

## 한 줄 정의

**여러 컴퓨터의 시계를 인터넷으로 동기화**하는 표준 프로토콜 (RFC 5905). 분산 시스템에서 시각 의존 알고리즘 ([[snowflake-id]], 시계 기반 quorum, sliding window rate limiter 등)의 전제 인프라.

## 왜 필요한가

분산 시스템의 각 머신은 자체 클럭으로 동작 — 하지만 **시간이 흐르면 서로 어긋남(drift)**. quartz crystal 기반 시계는 일반적으로 하루에 수 ms ~ 수 초씩 drift. 시각 차이가 분 단위로 커지면:

- **[[snowflake-id]]가 ID 충돌·역순 발생** — timestamp가 가장 상위 비트라 시계 뒤바뀌면 후행 ID가 선행보다 작아짐
- **분산 트랜잭션 timeout 오작동** — 머신 A가 "5초 지났다"고 보지만 B는 "1초만 지났다"
- **로그·트레이스 시각이 어긋나 디버깅 불가**
- **TLS 인증서 expire 시각 판단 깨짐**
- **rate limiter sliding window가 잘못 동작** (ch04: "*sliding window 계열은 Redis TIME으로 서버 시각 사용 — race 방지의 연장*")

NTP가 이 모든 문제의 1차 방어선.

## 핵심 메커니즘 (개요)

NTP 자체 디테일은 RFC 5905 / Wikipedia 참조. 시스템 설계 관점에서 알아야 할 것:

### Stratum 계층 구조

```
Stratum 0: GPS·원자시계 등 reference clock
   │
Stratum 1: stratum 0과 직접 연결된 NTP 서버 (가장 정확, μs 단위)
   │
Stratum 2: stratum 1과 동기화하는 서버
   │  ...
Stratum N (최대 15): 클라이언트가 사용하는 서버
```

각 stratum이 위 계층에서 시각 받아 보정. **계층이 멀어질수록 오차 누적** (보통 ms 단위).

### 시각 동기화 방식

클라이언트가 NTP 서버에 요청 → 4개 timestamp 측정:
- T1: 클라이언트 송신 시각
- T2: 서버 수신 시각
- T3: 서버 송신 시각
- T4: 클라이언트 수신 시각

→ Round-trip delay와 offset 계산 → 클라이언트 시계 보정. **여러 NTP 서버 평균 + 이상치 제거**로 정확도 ↑.

### 보정 방식 — slew vs step

- **slew**: 시계를 천천히 조정 (μs 단위 변화) — 평소 사용
- **step**: 큰 차이는 한 번에 점프 — 분 단위 차이 발생 시. **시계가 뒤로 점프할 수 있음** ← 분산 알고리즘에 문제

## 트레이드오프 & 한계

### 정확도

| 환경 | 일반적 정확도 |
|---|---|
| 로컬 stratum 1 서버 (자체 NTP 서버 운영) | μs ~ ms |
| 인터넷 공공 NTP (pool.ntp.org) | 1~50ms |
| 클라우드 NTP (AWS Time Sync, Google Public NTP) | 1ms 이하 |
| leap second 이벤트 | 시계가 뒤로 1초 점프 가능 (smear 안 하면) |

### 한계

- **시계가 뒤로 갈 수 있음** — leap second·운영자 수동 설정·VM resume·NTP step 보정 시. snowflake 같은 알고리즘은 별도 방어 필요
- **인터넷 지연 의존** — RTT가 비대칭(asymmetric latency)이면 보정 오차
- **방어 없는 서버는 NTP amplification DDoS의 reflector** — 운영 시 monlist 비활성화 등 필요
- **virtual machine 환경의 정확도 ↓** — 호스트 시계에 의존, hypervisor가 가상 클럭 인터럽트 놓치면 drift

### NTP의 대안·확장

- **PTP (Precision Time Protocol)** — 데이터센터 내부에서 μs 정확도 필요할 때 (금융·하드웨어 timestamping)
- **TrueTime (Google Spanner)** — GPS + 원자시계로 시계 오차 범위 보장 → strong consistency 분산 트랜잭션 가능
- **HLC (Hybrid Logical Clock)** — 물리 시계 + 논리 시계 결합. CockroachDB 등에서 사용

## 실무 적용 시 고려사항

1. **클라우드면 platform-provided NTP** — AWS Time Sync (`169.254.169.123`), GCP `metadata.google.internal` 등. 대기시간·정확도 모두 최적
2. **자체 데이터센터면 자체 stratum 1·2 서버 구축** — GPS·원자시계 1대 + 내부 NTP 분산. 인터넷 NTP 의존하면 정확도·가용성 모두 약함
3. **leap second smear 채택** — Google·AWS는 leap second 발생 시 24시간 동안 천천히 분산. 시계 뒤점프 없음. 자체 운영하면 같은 패턴 권장
4. **시각 의존 알고리즘은 뒤점프 방어 필수** — snowflake·HLC·trxn time 등 모두 `if now < last: ...` 분기 가짐
5. **모니터링** — `ntpq -p` (또는 `chronyc tracking`)로 stratum·offset·jitter 추적. 1초 이상 offset 발생하면 alert
6. **컨테이너 시각** — Docker 컨테이너는 호스트 시계 공유. 호스트가 정확하면 컨테이너도 OK. 별도 NTP 안 돌려도 됨

## 다른 개념과의 관계

- [[snowflake-id]] (ch07) — timestamp 41-bit가 NTP 정확도에 의존. 시계 뒤점프 시 충돌
- [[ch04-rate-limiter]] — sliding window 계열이 시각 비교. Redis `TIME` 사용 (NTP 동기화된 서버 시각)
- [[quorum-consensus]] (ch06) — strong consistency를 위한 timestamp ordering에 NTP 정확도 필요
- [[multi-data-center]] (ch01) — DC 간 데이터 동기화에서 시각 정렬

## 등장 사례

- ch04 — sliding window log·counter가 "Redis TIME 사용 (서버 시각)" 명시. 그 서버 시각은 NTP 동기화 결과
- ch07 — snowflake의 timestamp section이 NTP 인프라 전제. p.117 wrap up: "*Clock synchronization. In our design, we assume ID generation servers have the same clock. ... Network Time Protocol is the most popular solution to this problem.*"
- 모든 distributed tracing 시스템 — span 시각 정렬 (Jaeger, Zipkin, OpenTelemetry)
- Kafka — 메시지 timestamp ordering
- 로그 집계 (ELK, Splunk) — 다중 서버 로그 시간순 정렬
- TLS·OAuth token expiration 판단

## 면접 관점 메모

NTP 자체를 직접 다루는 면접 질문은 드물지만, **시각 의존 알고리즘**(snowflake·sliding window·distributed tx) 질문에서 "*시계가 어떻게 동기화되나요?*" 답할 수 있어야. "NTP 가정한다 + leap second·시계 뒤점프 방어 필요" 두 문장으로 충분.
