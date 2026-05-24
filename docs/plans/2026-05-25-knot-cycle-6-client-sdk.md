# knot Cycle 6 — 클라이언트 SDK 미니 구현 계획

> **For agentic workers:** Use superpowers:subagent-driven-development.

**Goal:** [[ch04-rate-limiter]] §"클라이언트 모범 사례" 4가지 권고(캐시·한도 인지·우아한 429·exponential backoff)를 SDK로 구현. naive httpx 클라이언트와 같은 부하로 비교해 클라이언트 측 대응의 정량 효과 시연.

**Architecture:** `experiments/knot/client/` 패키지. `NaiveClient`(baseline)와 `KnotClient`(4 권고 적용) 두 클래스. `scripts/compare_clients.py`로 두 시나리오(캐시 효과·backoff 효과) 비교 실행. `respx`로 unit test의 mock httpx.

**Spec:** `docs/specs/2026-05-25-knot-cycle-6-client-sdk-design.md` (결정 이력 10개).

**Scope (5 task)**:
1. 의존성(`respx`) + NaiveClient + KnotClient (TDD, 5 unit)
2. compare_clients.py 스크립트 (두 시나리오)
3. 비교 실행 + reports/client_comparison.md
4. wiki cycle 6 섹션
5. spec status + log + push + PR

---

## File Structure

```
신규:
  client/__init__.py
  client/base.py             # 공통 dataclass: ShortenResult, RateLimitedResult
  client/naive.py            # NaiveClient (baseline)
  client/sdk.py              # KnotClient (cache + backoff + Throttled 인지)
  scripts/compare_clients.py
  tests/unit/test_knot_client.py
  reports/client_comparison.md (+ JSON, T3 생성)

변경:
  pyproject.toml             # respx dev
```

---

## Task 1: 의존성 + NaiveClient + KnotClient + unit (TDD)

**Files:**
- Modify: `experiments/knot/pyproject.toml` (respx 추가)
- Create: `experiments/knot/client/{__init__,base,naive,sdk}.py`
- Test: `experiments/knot/tests/unit/test_knot_client.py`

- [ ] **Step 1: pyproject.toml dev deps에 respx 추가**

```toml
dev = [
    ...
    "respx>=0.21",
    ...
]
```

`uv sync`.

- [ ] **Step 2: client 디렉터리 + base.py**

```bash
mkdir -p experiments/knot/client
touch experiments/knot/client/__init__.py
```

```python
# experiments/knot/client/base.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ShortenResult:
    code: str
    limit: int                          # X-Ratelimit-Limit
    remaining: int                      # X-Ratelimit-Remaining
    throttled: bool                     # X-Ratelimit-Throttled
    throttle_ms: int                    # X-Ratelimit-Throttle-Ms (있을 때)
    cached: bool = False                # SDK 내부 캐시 히트 여부


@dataclass
class RateLimitedResult:
    retry_after: float                  # 초
    limit: int
    raw_status: int = 429
```

- [ ] **Step 3: NaiveClient (baseline, 단순)**

```python
# experiments/knot/client/naive.py
from __future__ import annotations

import httpx

from app.limiter.base import Decision  # 안 씀, 참고용 — 실제로 import 안 함
from client.base import RateLimitedResult, ShortenResult


class NaiveClient:
    """httpx wrapper. 캐시·backoff 없음. 429 받으면 RateLimitedResult 반환."""

    def __init__(self, base_url: str, api_key: str = "", user_tier: str = "default") -> None:
        self._client = httpx.AsyncClient(base_url=base_url)
        self._headers = {"x-api-key": api_key, "x-user-tier": user_tier}

    async def shorten(self, url: str) -> ShortenResult | RateLimitedResult:
        r = await self._client.post(
            "/shorten",
            json={"url": url},
            headers={**self._headers, "content-type": "application/json"},
        )
        if r.status_code == 429:
            return RateLimitedResult(
                retry_after=float(r.headers.get("x-ratelimit-retry-after", 0)),
                limit=int(r.headers.get("x-ratelimit-limit", 0)),
            )
        body = r.json()
        return ShortenResult(
            code=body["code"],
            limit=int(r.headers.get("x-ratelimit-limit", 0)),
            remaining=int(r.headers.get("x-ratelimit-remaining", 0)),
            throttled=r.headers.get("x-ratelimit-throttled") == "true",
            throttle_ms=int(r.headers.get("x-ratelimit-throttle-ms", 0)),
        )

    async def aclose(self) -> None:
        await self._client.aclose()
```

- [ ] **Step 4: KnotClient (4 권고 적용)**

```python
# experiments/knot/client/sdk.py
from __future__ import annotations

import asyncio
import time

import httpx

from client.base import RateLimitedResult, ShortenResult

CACHE_TTL_S = 5 * 60       # 5분
MAX_ATTEMPTS = 4
MAX_BACKOFF_S = 60
BASE_BACKOFF_S = 1


class KnotClient:
    def __init__(self, base_url: str, api_key: str = "", user_tier: str = "default") -> None:
        self._client = httpx.AsyncClient(base_url=base_url)
        self._headers = {"x-api-key": api_key, "x-user-tier": user_tier}
        self._cache: dict[str, tuple[ShortenResult, float]] = {}
        self._next_request_at = 0.0    # Throttled 헤더 받으면 미래 시각

        # 관측 가능 메트릭
        self.cache_hits = 0
        self.server_calls = 0
        self.backoff_waits = 0

    async def shorten(self, url: str) -> ShortenResult | RateLimitedResult:
        # 권고 ① 캐시
        if url in self._cache:
            result, expires_at = self._cache[url]
            if time.time() < expires_at:
                self.cache_hits += 1
                cached_result = ShortenResult(
                    code=result.code,
                    limit=result.limit,
                    remaining=result.remaining,
                    throttled=False,
                    throttle_ms=0,
                    cached=True,
                )
                return cached_result

        # 권고 ⑤ — 이전 응답이 throttled였으면 다음 호출 전 대기
        now = time.time()
        if now < self._next_request_at:
            await asyncio.sleep(self._next_request_at - now)

        # 권고 ④ — backoff 재시도
        for attempt in range(MAX_ATTEMPTS):
            self.server_calls += 1
            r = await self._client.post(
                "/shorten",
                json={"url": url},
                headers={**self._headers, "content-type": "application/json"},
            )

            if r.status_code == 200:
                body = r.json()
                result = ShortenResult(
                    code=body["code"],
                    limit=int(r.headers.get("x-ratelimit-limit", 0)),
                    remaining=int(r.headers.get("x-ratelimit-remaining", 0)),
                    throttled=r.headers.get("x-ratelimit-throttled") == "true",
                    throttle_ms=int(r.headers.get("x-ratelimit-throttle-ms", 0)),
                )
                # 권고 ② — 한도 인지: throttled면 다음 호출 늦춤
                if result.throttled:
                    self._next_request_at = time.time() + result.throttle_ms / 1000
                # 권고 ① — 캐시 저장
                self._cache[url] = (result, time.time() + CACHE_TTL_S)
                return result

            if r.status_code == 429:
                if attempt == MAX_ATTEMPTS - 1:
                    return RateLimitedResult(
                        retry_after=float(r.headers.get("x-ratelimit-retry-after", 0)),
                        limit=int(r.headers.get("x-ratelimit-limit", 0)),
                    )
                # Retry-After 우선, 없으면 지수
                retry_after = float(r.headers.get("x-ratelimit-retry-after", 0))
                if retry_after > 0:
                    wait = min(retry_after, MAX_BACKOFF_S)
                else:
                    wait = min(BASE_BACKOFF_S * (2 ** attempt), MAX_BACKOFF_S)
                self.backoff_waits += 1
                await asyncio.sleep(wait)
                continue

            # 다른 status code (5xx 등)
            r.raise_for_status()

        # 도달 못 함
        raise RuntimeError("unreachable")

    async def aclose(self) -> None:
        await self._client.aclose()
```

- [ ] **Step 5: 5 unit tests (TDD red-green)**

```python
# experiments/knot/tests/unit/test_knot_client.py
from __future__ import annotations

import time

import httpx
import pytest
import respx
from freezegun import freeze_time

from client.naive import NaiveClient
from client.sdk import KnotClient, CACHE_TTL_S


@pytest.fixture
def mock_route():
    with respx.mock(base_url="http://test") as router:
        yield router


@pytest.mark.asyncio
async def test_naive_shorten_returns_response(mock_route):
    mock_route.post("/shorten").mock(return_value=httpx.Response(
        200, json={"code": "abc123"},
        headers={"x-ratelimit-limit": "10", "x-ratelimit-remaining": "9"},
    ))
    client = NaiveClient(base_url="http://test", api_key="k")
    result = await client.shorten("https://e.com")
    assert result.code == "abc123"
    assert result.limit == 10
    assert result.remaining == 9
    await client.aclose()


@pytest.mark.asyncio
async def test_sdk_cache_hit_skips_server(mock_route):
    route = mock_route.post("/shorten").mock(return_value=httpx.Response(
        200, json={"code": "abc123"},
        headers={"x-ratelimit-limit": "10", "x-ratelimit-remaining": "9"},
    ))
    client = KnotClient(base_url="http://test")
    # 첫 호출 — 서버 호출
    r1 = await client.shorten("https://e.com")
    assert r1.cached is False
    assert route.call_count == 1
    # 두 번째 호출 — 캐시 히트, 서버 호출 X
    r2 = await client.shorten("https://e.com")
    assert r2.cached is True
    assert r2.code == "abc123"
    assert route.call_count == 1     # 여전히 1
    assert client.cache_hits == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_sdk_cache_expires_after_ttl(mock_route):
    route = mock_route.post("/shorten").mock(return_value=httpx.Response(
        200, json={"code": "abc123"},
        headers={"x-ratelimit-limit": "10", "x-ratelimit-remaining": "9"},
    ))
    client = KnotClient(base_url="http://test")
    with freeze_time("2026-05-25 12:00:00") as ft:
        await client.shorten("https://e.com")
        assert route.call_count == 1
        # TTL 직전엔 캐시
        ft.tick(CACHE_TTL_S - 1)
        r = await client.shorten("https://e.com")
        assert r.cached is True
        assert route.call_count == 1
        # TTL 지나면 다시 서버 호출
        ft.tick(2)
        r = await client.shorten("https://e.com")
        assert r.cached is False
        assert route.call_count == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_sdk_backoff_on_429(mock_route):
    """첫 응답 429 → backoff 후 200 → 정상 결과 반환."""
    responses = [
        httpx.Response(429, headers={"x-ratelimit-retry-after": "0.01", "x-ratelimit-limit": "10"}),
        httpx.Response(200, json={"code": "after-retry"},
                       headers={"x-ratelimit-limit": "10", "x-ratelimit-remaining": "9"}),
    ]
    mock_route.post("/shorten").mock(side_effect=responses)

    client = KnotClient(base_url="http://test")
    result = await client.shorten("https://e.com")
    # backoff 후 두 번째 응답이 200이라 ShortenResult 받음
    assert hasattr(result, "code")
    assert result.code == "after-retry"
    assert client.backoff_waits == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_sdk_throttle_header_delays_next_request(mock_route):
    """200 + Throttled 응답 받으면 다음 호출 전 대기."""
    mock_route.post("/shorten").mock(return_value=httpx.Response(
        200, json={"code": "x"},
        headers={
            "x-ratelimit-limit": "50",
            "x-ratelimit-remaining": "0",
            "x-ratelimit-throttled": "true",
            "x-ratelimit-throttle-ms": "100",   # 100ms delay 지정
        },
    ))
    client = KnotClient(base_url="http://test")
    await client.shorten("https://a.com")
    # 다른 URL로 두 번째 호출 (캐시 미스로 서버 호출 강제)
    start = time.perf_counter()
    await client.shorten("https://b.com")
    elapsed = time.perf_counter() - start
    # 100ms 대기 + 호출 시간
    assert elapsed >= 0.08, f"elapsed {elapsed*1000:.0f}ms — expected ≥80ms (throttle delay)"
    await client.aclose()
```

- [ ] **Step 6: 실패 → 통과 확인**

Run: `cd experiments/knot && uv run pytest tests/unit/test_knot_client.py -v`

처음엔 module import 실패. base.py·naive.py·sdk.py 작성 후 5 passed.

전체 suite:
```bash
docker compose up -d redis
docker compose exec -T redis redis-cli FLUSHALL
REDIS_AVAILABLE=1 uv run pytest -v
```
Expected: 49 passed (cycle 0-5: 44 + cycle 6 unit: 5).

- [ ] **Step 7: 커밋**

```bash
git add experiments/knot/pyproject.toml experiments/knot/uv.lock \
        experiments/knot/client \
        experiments/knot/tests/unit/test_knot_client.py
git commit -m "experiment: knot cycle 6 - NaiveClient + KnotClient (4 권고 적용) + unit 5개"
```

---

## Task 2: compare_clients.py 스크립트

**Files:**
- Create: `experiments/knot/scripts/compare_clients.py`

- [ ] **Step 1: 스크립트 작성**

```python
# experiments/knot/scripts/compare_clients.py
"""
NaiveClient vs KnotClient 비교 부하 시험.

사용:
  uv run python scripts/compare_clients.py --scenario cache_effect --base-url http://localhost:8001
  uv run python scripts/compare_clients.py --scenario backoff_effect --base-url http://localhost:8001 --user-tier premium
"""

from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import time
from typing import Any

from client.naive import NaiveClient
from client.sdk import KnotClient


async def _run_cache_scenario(client_factory, base_url: str, api_key: str) -> dict[str, Any]:
    """같은 URL을 100번 shorten."""
    client = client_factory(base_url, api_key=api_key, user_tier="free")
    url = f"https://e.com/test-{secrets.token_hex(4)}"

    start = time.perf_counter()
    successes = 0
    rate_limited = 0
    for _ in range(100):
        result = await client.shorten(url)
        if hasattr(result, "code"):
            successes += 1
        else:
            rate_limited += 1
    elapsed = time.perf_counter() - start

    stats = {
        "successes": successes,
        "rate_limited": rate_limited,
        "total_seconds": round(elapsed, 2),
    }
    if hasattr(client, "cache_hits"):
        stats["cache_hits"] = client.cache_hits
        stats["server_calls"] = client.server_calls

    await client.aclose()
    return stats


async def _run_backoff_scenario(client_factory, base_url: str, api_key: str, user_tier: str) -> dict[str, Any]:
    """다른 URL 60번을 1초 간격으로."""
    client = client_factory(base_url, api_key=api_key, user_tier=user_tier)

    start = time.perf_counter()
    successes = 0
    rate_limited = 0
    throttled = 0
    for i in range(60):
        url = f"https://e.com/req-{i}"
        result = await client.shorten(url)
        if hasattr(result, "code"):
            successes += 1
            if result.throttled:
                throttled += 1
        else:
            rate_limited += 1
        # 다음 호출까지 1초 대기 (전체 ~60s)
        await asyncio.sleep(1.0)
    elapsed = time.perf_counter() - start

    stats = {
        "successes": successes,
        "rate_limited": rate_limited,
        "throttled_responses": throttled,
        "total_seconds": round(elapsed, 2),
    }
    if hasattr(client, "backoff_waits"):
        stats["backoff_waits"] = client.backoff_waits
        stats["server_calls"] = client.server_calls

    await client.aclose()
    return stats


def _print_table(scenario: str, naive: dict, sdk: dict) -> None:
    print(f"\n=== Scenario: {scenario} ===")
    keys = sorted(set(naive.keys()) | set(sdk.keys()))
    print(f"{'metric':<25} {'NaiveClient':>15} {'KnotClient':>15}")
    print("-" * 60)
    for k in keys:
        n = naive.get(k, "-")
        s = sdk.get(k, "-")
        print(f"{k:<25} {str(n):>15} {str(s):>15}")


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", choices=["cache_effect", "backoff_effect", "both"], default="both")
    p.add_argument("--base-url", default="http://localhost:8001")
    p.add_argument("--user-tier", default="free")
    p.add_argument("--output", default=None, help="JSON 출력 경로")
    args = p.parse_args()

    results: dict[str, Any] = {}

    if args.scenario in ("cache_effect", "both"):
        naive_key = f"cache-naive-{secrets.token_hex(2)}"
        sdk_key = f"cache-sdk-{secrets.token_hex(2)}"
        naive_stats = await _run_cache_scenario(NaiveClient, args.base_url, naive_key)
        sdk_stats = await _run_cache_scenario(KnotClient, args.base_url, sdk_key)
        _print_table("cache_effect (same URL ×100)", naive_stats, sdk_stats)
        results["cache_effect"] = {"naive": naive_stats, "sdk": sdk_stats}

    if args.scenario in ("backoff_effect", "both"):
        naive_key = f"backoff-naive-{secrets.token_hex(2)}"
        sdk_key = f"backoff-sdk-{secrets.token_hex(2)}"
        naive_stats = await _run_backoff_scenario(NaiveClient, args.base_url, naive_key, args.user_tier)
        sdk_stats = await _run_backoff_scenario(KnotClient, args.base_url, sdk_key, args.user_tier)
        _print_table(f"backoff_effect (60 reqs spread, tier={args.user_tier})", naive_stats, sdk_stats)
        results["backoff_effect"] = {"naive": naive_stats, "sdk": sdk_stats}

    if args.output:
        from pathlib import Path
        Path(args.output).write_text(json.dumps(results, indent=2))
        print(f"\nwrote {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: import 검증**

```bash
cd experiments/knot && uv run python -c "import scripts.compare_clients; print('ok')"
```

- [ ] **Step 3: 커밋**

```bash
git add experiments/knot/scripts/compare_clients.py
git commit -m "experiment: knot cycle 6 - compare_clients.py (cache_effect + backoff_effect 시나리오)"
```

---

## Task 3: 비교 실행 + reports/client_comparison.md

**Files:**
- Create: `experiments/knot/reports/client_comparison.md` (+ JSON)

- [ ] **Step 1: app background + Redis 정리**

```bash
cd /Users/fetching/study/system-design/experiments/knot
docker compose up -d redis
docker compose exec -T redis redis-cli FLUSHALL

uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 > /tmp/knot_c6_app.log 2>&1 &
APP_PID=$!
sleep 3
curl -sf http://localhost:8001/healthz | head -1
```

- [ ] **Step 2: cache_effect 시나리오**

```bash
mkdir -p out
uv run python scripts/compare_clients.py \
  --scenario cache_effect \
  --base-url http://localhost:8001 \
  --output out/cache_effect.json
```

기대 결과:
- naive: 10 success / 90 rate_limited (free 10/min 한도)
- SDK: 100 success / 0 rate_limited, cache_hits=99, server_calls=1

- [ ] **Step 3: backoff_effect 시나리오 (premium tier, ~60초 소요)**

⚠️ 각 시나리오마다 Redis 정리:

```bash
docker compose exec -T redis redis-cli FLUSHALL

uv run python scripts/compare_clients.py \
  --scenario backoff_effect \
  --base-url http://localhost:8001 \
  --user-tier premium \
  --output out/backoff_effect.json
```

기대 결과 (premium 50/min, 1초 간격 60회):
- 60초 동안 분산하면 50/min 안에 들어옴 → naive·SDK 둘 다 거의 100% 통과
- 다만 ~51번째 즈음에 윈도우 안 누적이 50 도달 → 429 또는 Throttled 발생 가능
- SDK는 backoff 재시도로 결국 통과 vs naive 포기

(실측 결과 보고 wiki 본문에 정직하게 박을 것)

- [ ] **Step 4: 앱 종료**

```bash
kill $APP_PID 2>/dev/null
```

- [ ] **Step 5: 리포트 작성**

`experiments/knot/reports/client_comparison.md`:

```markdown
# Client SDK vs Naive 비교 — cycle 6

> ch04 §"클라이언트 모범 사례" 4가지 권고를 KnotClient에 적용. NaiveClient는
> baseline (httpx wrapper만).

## 시나리오 A — 캐시 효과 (같은 URL ×100, free tier)

(out/cache_effect.json 결과 표로 옮기기)

## 시나리오 B — backoff 효과 (60 reqs 1초 간격, premium tier)

(out/backoff_effect.json 결과 표로 옮기기)

## 결론

(naive vs SDK 차이 정량 정리)
```

실측 본 후 본문 채울 것 — 가정으로 적지 말고 출력값 그대로.

- [ ] **Step 6: out/은 gitignored 확인**

```bash
grep -q "out/" experiments/knot/.gitignore || echo "out/" >> experiments/knot/.gitignore
```

- [ ] **Step 7: 커밋**

```bash
git add experiments/knot/reports/client_comparison.md experiments/knot/.gitignore
git commit -m "experiment: knot cycle 6 - 비교 실행 + reports/client_comparison.md"
```

---

## Task 4: wiki cycle 6 섹션

**Files:**
- Modify: `wiki/projects/knot.md`

- [ ] **Step 1: 섹션 append (T3 실측치 반영)**

```markdown

## Cycle 6 — 클라이언트 SDK 미니

**목표**: [[ch04-rate-limiter]] §"클라이언트 모범 사례" 4가지 권고(캐시·한도 인지·우아한 429·exponential backoff)를 SDK로 구현. naive 클라이언트와 비교로 클라이언트 측 대응의 정량 효과 시연.

**산출**: 5 task, 49 tests (이전 44 + client unit 5). `experiments/knot/client/` 패키지 신규.

**Sub-spec**: `docs/specs/2026-05-25-knot-cycle-6-client-sdk-design.md` (결정 이력 10개).

### 4가지 권고 구현

| 권고 | 구현 |
|---|---|
| ① 응답 캐시 | URL → response 5분 TTL in-memory dict |
| ② 한도 인지 | 응답 헤더 추적 (`X-Ratelimit-Limit/Remaining/Throttled`) |
| ③ 우아한 429 | `RateLimitedResult` dataclass로 명시적 반환 (예외 X) |
| ④ Exponential backoff | base=1s, factor=2, max=60s, 4 attempts. `Retry-After` 헤더 우선 |
| ⑤ Throttled 인지 (cycle 5 헤더 활용) | 200 + Throttled 받으면 다음 호출 전 자동 대기 |

### 비교 실측 결과

(T3 출력 정리해서 박기 — cache_effect / backoff_effect 표 두 개)

### 핵심 발견

(실측 본 후 — 예: 캐시 효과는 99% 부하 감소, backoff는 ~X% 성공률 향상 등)

### Cycle 6 회고

knot 운영 stack 완성 — 서버 측 rate limiter(cycle 0~5)와 클라이언트 측 대응(cycle 6)이 상보적으로 작동:
- 서버: 정확한 한도 enforcement + 표준 헤더
- 클라이언트: 헤더 인지로 자제·재시도·캐싱

남은 cycle 7: 회고 (스킵된 알고리즘 정리 + ch04 후반 토픽).
```

T3 실측치 보고 (실측치)·(핵심 발견)·(회고) 부분 정직하게 채움.

- [ ] **Step 2: 커밋**

```bash
git add wiki/projects/knot.md
git commit -m "docs: wiki/projects/knot.md - cycle 6 (client SDK) 섹션 append"
```

---

## Task 5: spec status + log + push + PR

**Files:**
- Modify: `docs/specs/2026-05-24-rate-limiter-design.md`
- Modify: `log.md`

- [ ] **Step 1: spec §7 cycle 6 done**

cycle 6 행 status: `todo` → `done (2026-05-25)`

- [ ] **Step 2: log.md append**

```markdown

## [2026-05-25] experiment | knot cycle 6: 클라이언트 SDK 미니

[[ch04-rate-limiter]] §"클라이언트 모범 사례" 4가지 권고를 KnotClient로 구현. naive 클라이언트와 비교 실측. 캐시 효과: 같은 URL ×100 시나리오에서 SDK는 1번만 서버 호출(99 캐시 히트) vs naive는 100번 다 호출(10 통과 / 90 429). backoff 효과: premium tier 60 reqs 시 SDK는 Retry-After 존중 재시도로 거의 100% 통과 vs naive는 한도 도달 후 포기. 49 tests passing.

- `experiments/knot/client/` 패키지 신규 (base/naive/sdk)
- `scripts/compare_clients.py` + `reports/client_comparison.md`
- 결정 이력: spec `docs/specs/2026-05-25-knot-cycle-6-client-sdk-design.md` §6

cycle 7: 회고 (스킵된 알고리즘 + multi-DC·OSI L3·edge 배치).
```

(실측 결과 다르면 정확히 반영)

- [ ] **Step 3: 커밋 + push + PR**

```bash
git add docs/specs/2026-05-24-rate-limiter-design.md log.md
git commit -m "experiment: knot cycle 6 완료 — spec + log"
git push -u origin experiment/knot-cycle-6

gh pr create --base main --head experiment/knot-cycle-6 \
  --title "experiment: knot cycle 6 (클라이언트 SDK 미니)" \
  --body "..."
```

PR body는 4가지 권고 구현 + 실측 비교 결과 요약.

---

## 검증 체크리스트

- [ ] `REDIS_AVAILABLE=1 uv run pytest -v` 49 passed
- [ ] cache_effect: SDK가 naive보다 서버 호출 ≥90% 감소
- [ ] backoff_effect: SDK가 naive보다 성공률 ↑ (정확한 차이는 실측 후)
- [ ] `reports/client_comparison.md` 두 시나리오 표 포함
- [ ] PR 생성

## 다음 사이클

**Cycle 7 — 회고**: 스킵된 알고리즘 (leaking_bucket·sliding_window_counter) wiki 글, ch04 후반 토픽(multi-DC·OSI L3·edge 배치) 위치 정리, 위키 cross-link 일괄 갱신. ~3 task.
