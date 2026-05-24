# knot Cycle 5 — Hard vs Soft 정책 설계

- **문서 종류**: Sub-spec (cycle 5, 짧은 사이클)
- **상위 spec**: `docs/specs/2026-05-24-rate-limiter-design.md`
- **작성일**: 2026-05-24
- **관련 위키**: [[rate-limiting]] (§"hard vs soft"), [[ch04-rate-limiter]] §"추가 토픽"
- **상태**: 작성 직후

## 0. 목적과 학습 의도

[[ch04-rate-limiter]] §"추가 토픽 — hard vs soft rate limiting"은 한 단락만 다뤄짐:

> "**hard = 임계 초과 절대 불가, soft = 단기 초과 허용**. 사용자 경험과 보호 강도 사이 트레이드오프."

cycle 5는 이 한 단락을 코드로 풀어내고, **knot의 premium tier에 soft 정책을 적용해 "한도 넘어도 차단 대신 잠시 느려짐"의 그래프 증명**.

핵심: 알고리즘 코드 변경 0줄. cycle 0부터 박혀있던 `Rule.mode` 필드(`"hard" | "soft"`)가 5 사이클만에 활성화됨. middleware가 mode 분기.

### 무엇이 달라지나

| | cycle 4까지 | cycle 5 |
|---|---|---|
| 한도 초과 시 | 모든 정책 즉시 **429** | hard: 429 / **soft: throttle 후 200** |
| `shorten` premium | 분당 50, hard | 분당 50, **soft** — 51번째 요청은 ~600ms 지연 후 200 |
| `shorten` free | 분당 10, hard | 변경 없음 |
| `redirect` | 50/s, hard | 변경 없음 |
| 알고리즘 코드 | — | 0줄 변경 (middleware만) |

## 1. Soft mode의 동작 정의

### 1-1. Throttle 방식

```
한도 초과 + mode=soft → asyncio.sleep(throttle_ms) → 핸들러 실행 → 200 응답
```

- `throttle_ms` = `min(decision.retry_after * 1000, MAX_THROTTLE_MS)` — limiter가 계산한 정확한 재시도 시각까지 대기, 단 cap
- `MAX_THROTTLE_MS = 2000ms` — 무한 대기 방지. 초과 시 hard처럼 429로 fallback (long-throttle을 거부로 변환)
- Throttle 후 핸들러는 **정상 실행** (시간 흐른 후라 다음 token이 회복되어 있을 가능성 ↑). 즉 throttle = "기다리면 통과시켜준다"

### 1-2. 카운터에 가산하지 않음

핵심 결정: **throttled 요청은 limiter counter에 추가하지 않음**.

- 이유: limiter.allow()가 deny를 반환했으므로 counter는 변경 없음 (token bucket: token 차감 X / sliding window log: ZADD 안 됨)
- 의미: soft mode = "한도는 유지하되 거부 대신 지연으로 표현". 카운터 정확성은 그대로
- 대안(throttle 후 force-add)을 고르면 counter가 무한 누적 → 메모리 누수. 학습 목적이라도 피함

### 1-3. 응답 헤더

| 헤더 | 값 (throttled 200) |
|---|---|
| `X-Ratelimit-Limit` | 정책 한도 |
| `X-Ratelimit-Remaining` | `0` (이번 윈도우 한도 소진) |
| `X-Ratelimit-Throttled` | `true` (cycle 5 신설) |
| `X-Ratelimit-Throttle-Ms` | 실제 sleep한 ms (디버깅·관측용) |

`X-Ratelimit-Throttled` — 클라이언트 SDK(cycle 6)가 "한도 hit" 신호로 사용. 200이지만 응답 느림 + 헤더로 "내가 throttle됐다" 확인 가능 → exponential backoff 트리거.

## 2. Middleware 분기

```python
# app/middleware.py — dispatch() 안 (의사코드)
decision = await limiter.allow(key, rule)

if decision.allowed:
    # cycle 0~4 동일 — 정상 통과
    response = await call_next(request)
    response.headers["X-Ratelimit-Limit"] = str(decision.limit)
    response.headers["X-Ratelimit-Remaining"] = str(decision.remaining)
    return response

# Denied — 여기서 mode 분기
if rule.mode == "soft":
    throttle_ms = min(int(decision.retry_after * 1000), MAX_THROTTLE_MS)
    if throttle_ms >= MAX_THROTTLE_MS:
        # 너무 길어지면 hard처럼 거부 (장기 폭주 보호)
        return _deny_response(decision)

    await asyncio.sleep(throttle_ms / 1000)
    response = await call_next(request)
    response.headers["X-Ratelimit-Limit"] = str(decision.limit)
    response.headers["X-Ratelimit-Remaining"] = "0"
    response.headers["X-Ratelimit-Throttled"] = "true"
    response.headers["X-Ratelimit-Throttle-Ms"] = str(throttle_ms)
    return response

# mode == "hard" (default)
return _deny_response(decision)
```

`_deny_response`는 기존 429 응답 헬퍼로 분리 — 중복 제거.

## 3. rules.yaml 변경

```yaml
descriptors:
  - key: endpoint
    value: shorten
    descriptors:
      - key: user_tier
        value: premium
        rate_limit:
          algorithm: sliding_window_log
          unit: minute
          requests_per_unit: 50
          mode: soft                           # ← cycle 5 추가
      - key: user_tier
        value: enterprise
        rate_limit:
          algorithm: sliding_window_log
          unit: minute
          requests_per_unit: 500
          # enterprise는 hard 유지 (대량 사용자라 거부가 명확해야 함)
    rate_limit:
      algorithm: sliding_window_log
      unit: minute
      requests_per_unit: 10
      # free default도 hard
  - key: endpoint
    value: redirect
    rate_limit:
      algorithm: token_bucket
      unit: second
      requests_per_unit: 50
      burst: 100
```

비즈니스 시그널: **premium = 유료 = UX 우선 = soft**. free·enterprise·redirect는 hard 유지.

## 4. 테스트 전략

### Unit (`tests/unit/test_middleware_mode.py`) 3개

middleware의 mode 분기 격리 테스트 — limiter를 stub으로 갈아끼워 deny 케이스에서 hard/soft 분기 검증.

| 테스트 | 검증 |
|---|---|
| `test_hard_mode_denies_with_429` | mode=hard일 때 deny → 429 + headers (기존 동작) |
| `test_soft_mode_throttles_with_200` | mode=soft일 때 deny → sleep retry_after → 200 + Throttled header |
| `test_soft_mode_too_long_falls_back_to_hard` | retry_after > MAX_THROTTLE_MS → 429 (장기 폭주 보호) |

### Integration (`tests/integration/test_hard_soft_e2e.py`) 3개

| 테스트 | 검증 |
|---|---|
| `test_free_tier_hard_429` | tier=free 11번째 → 429 + Retry-After (이전 동작) |
| `test_premium_tier_soft_throttle` | tier=premium 51번째 → 200 + `X-Ratelimit-Throttled: true` + 측정 응답 시간 > 400ms |
| `test_premium_throttle_then_normal` | throttle 후 충분히 시간 지나 새 윈도우 → normal 200 (header 없음) |

시간 측정은 `time.perf_counter()` 기반.

## 5. 결정 이력 (Decision Log)

| # | 결정 | 선택 | 이유 |
|---|---|---|---|
| 1 | Soft 정의 | throttle = `asyncio.sleep` 후 200 통과 | ch04 §"단기 초과 허용"의 가장 직관적 형태. 응답 지연이 자연스러운 backoff 신호 |
| 2 | Throttle 시간 | `min(retry_after_ms, 2000ms)` cap | retry_after는 limiter가 계산한 정확한 시각. cap은 장기 폭주 방지 |
| 3 | Throttle 후 counter 동작 | **추가하지 않음** | limiter.allow가 deny 반환 = counter 변경 X. 일관성 유지, 메모리 누수 방지 |
| 4 | 응답 헤더 | `X-Ratelimit-Throttled: true` + `Throttle-Ms` | 클라이언트가 "throttled됨" 명시 인지. cycle 6 SDK가 backoff signal로 사용 |
| 5 | Throttle 너무 길면 | `MAX_THROTTLE_MS` 초과 시 429 fallback | 장기 폭주 사용자가 서버 thread를 무한 점유하는 것 방지 |
| 6 | Soft 적용 대상 | shorten premium tier만 | 유료=UX 우선. free·enterprise·redirect는 hard 유지 (비즈니스 시그널) |
| 7 | enterprise=hard 유지 | 대량 사용자는 거부가 명확해야 함 | 500/min 초과는 진짜 abuse — 지연으로 숨기지 않음 |
| 8 | Algorithm 코드 변경 | 0줄 | mode는 middleware가 처리. cycle 0 `Rule.mode` 필드 활성화만 |
| 9 | 테스트 — 시간 측정 | integration에서 `time.perf_counter` | sleep 동작을 실측해야 throttle 본질 검증 |
| 10 | Soft가 token bucket에도 의미 있나 | 의미는 있지만 본 사이클은 sliding_window_log(shorten)에만 적용 | redirect는 burst 허용이라 throttle보다 거부가 자연. 차후 확장 가능 |

## 6. 변경 파일

```
신규:
  experiments/knot/tests/unit/test_middleware_mode.py
  experiments/knot/tests/integration/test_hard_soft_e2e.py

변경:
  experiments/knot/app/middleware.py        # mode 분기, MAX_THROTTLE_MS, throttle 로직, _deny_response 헬퍼
  experiments/knot/rules.yaml               # premium에 mode: soft 한 줄
  wiki/projects/knot.md                     # ## Cycle 5 섹션
  docs/specs/2026-05-24-rate-limiter-design.md  # §7 cycle 5 done
  log.md                                    # cycle 5 항목
```

## 7. 미해결 / 후속

- **soft가 token bucket에 적용된다면 어떻게**: throttle = 가장 가까운 token 회복 시각까지 대기. 본 사이클 스코프 외, cycle 7 회고에서 짧게 언급
- **adaptive throttle**: 부하에 따라 throttle_ms를 동적 조정하는 발전형. 학습 범위 초과
- **소셜·검색 봇 같은 비대화형 클라이언트**: 응답 지연을 backoff로 받아들이지 않을 수 있음. cycle 6에서 클라이언트 SDK 패턴으로 다룸
