# Client SDK vs Naive 비교 — cycle 6

> ch04 §"클라이언트 모범 사례" 4가지 권고(① 응답 캐시, ② 한도 인지, ③ 우아한 429 처리, ④ exponential backoff + 재시도)를 `KnotClient`에 적용. `NaiveClient`는 baseline (httpx wrapper만, 헤더 추적·캐시·재시도 모두 없음).
>
> 실측 환경: `app/main.py` (uvicorn, port 8001) + Redis(docker compose). 시나리오 사이에 `FLUSHALL`로 상태 초기화. 원본 JSON은 `experiments/knot/out/` (gitignore).

## 시나리오 A — 캐시 효과 (같은 URL ×100, free tier)

동일 URL을 100번 연속 shorten 요청. free tier 한도(10/min) 안에서 클라이언트 측 캐시가 있는지/없는지를 본다.

| metric             | NaiveClient | KnotClient |
|--------------------|------------:|-----------:|
| successes          |          10 |        100 |
| rate_limited (429) |          90 |          0 |
| total_seconds      |        0.17 |       0.00 |
| cache_hits         |           — |         99 |
| server_calls       |           — |          1 |

- Naive: 처음 10개만 통과, 나머지 90개는 429. free tier 10/min 한도를 그대로 맞음.
- SDK: 첫 1회만 서버에 호출 → idempotent 결과를 in-process 캐시. 나머지 99회는 캐시 히트로 서버를 아예 건드리지 않음. 결과적으로 서버 부하 -99%, 성공률 10% → 100%.

## 시나리오 B — backoff 효과 (60 reqs, 1초 간격, premium tier)

premium tier(50/min)로 60개의 서로 다른 URL을 1초 간격으로 요청. 60req/60s가 50/min을 살짝 초과하는 구간으로 의도된 시나리오.

| metric              | NaiveClient | KnotClient |
|---------------------|------------:|-----------:|
| successes           |          52 |         60 |
| rate_limited (429)  |           8 |          0 |
| throttled_responses |           1 |          0 |
| total_seconds       |       62.02 |      70.09 |
| backoff_waits       |           — |          1 |
| server_calls        |           — |         61 |

- Naive: 60req 중 52개 성공, 8개는 429를 그대로 받고 버림 (재시도 없음). throttled_responses=1은 `RateLimit-Remaining=0` 응답을 한 번 받은 케이스(429와 별개 카운터).
- SDK: 429를 만나면 `Retry-After`를 존중해 대기 후 재시도. 결과적으로 backoff_wait 1회 발생 → 한 번 ~8초 잠시 멈춘 뒤 모든 요청 성공. total_seconds가 62 → 70초로 늘어난 부분이 그 대기 시간. server_calls=61은 1회 재시도가 추가된 것.

## 결론

- **캐시 효과**: SDK는 서버 호출을 100→1회(-99%)로 줄이며 성공률 10% → 100%로 끌어올림. idempotent 요청을 반복하는 패턴(같은 URL shorten 등)에서 효과 극단적.
- **backoff 효과**: SDK는 `Retry-After` 헤더를 존중해 대기 후 재시도하여 성공률 86.7% → 100% 달성. 대신 wall-clock은 62s → 70s로 약 13% 증가(요구 throughput을 강제로 한도에 맞춰 늦추기 때문이며 이게 의도).
- **클라이언트 측 대응은 서버 측 정책과 상보적**: 서버가 표준 헤더(`RateLimit-Limit/Remaining/Reset`, `Retry-After`)를 보내면 SDK가 자제·재시도·캐싱으로 대응 가능. 어느 한쪽만으로는 부족 — 서버가 한도를 알리지 않으면 SDK는 멍청하게 부딪쳐야 하고, SDK가 헤더를 무시하면 서버는 거부만 반복할 뿐 부하는 줄지 않는다.

## 시나리오 한계 및 후속

- backoff 시나리오는 premium 50/min에 60req/60s만 흘려 충돌이 적었음(429 8건). 더 가혹한 변형(예: free 10/min 한도에 30req/30s)을 돌리면 SDK 측 backoff_waits가 더 많이 누적되며 wall-clock 격차도 커질 것. 후속 사이클 후보.
- 캐시는 in-process 사전 기반이라 SDK 인스턴스 단위. 실제 운영 SDK라면 TTL·LRU·invalidation 정책이 추가되어야 함.
