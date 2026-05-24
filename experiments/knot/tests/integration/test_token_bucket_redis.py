# experiments/knot/tests/integration/test_token_bucket_redis.py
import asyncio

import pytest


@pytest.mark.asyncio
async def test_redirect_burst_absorption(client):
    """Burst capacity=100까지 통과, 그 다음은 429."""
    # 단축 코드 생성 (rate limit 영향 없도록 X-API-Key로 식별 분리)
    create = await client.post(
        "/shorten",
        json={"url": "https://example.com"},
        headers={"x-api-key": "burst-test"},
    )
    code = create.json()["code"]

    # 순차 100회 — capacity 안에 들어와야 함
    statuses = []
    for _ in range(105):
        r = await client.get(
            f"/{code}",
            headers={"x-api-key": "burst-test"},
            follow_redirects=False,
        )
        statuses.append(r.status_code)

    passed = sum(1 for s in statuses if s == 302)
    denied = sum(1 for s in statuses if s == 429)
    # rate가 50/s라 순차 호출 중 일부 refill 발생 → 최소 100개는 통과
    assert passed >= 100
    assert denied <= 5


@pytest.mark.asyncio
async def test_race_condition_atomic(client):
    """동시 200 요청에 정확히 capacity 개수만 통과 (Lua atomicity 증명)."""
    create = await client.post(
        "/shorten",
        json={"url": "https://example.com"},
        headers={"x-api-key": "race-test"},
    )
    code = create.json()["code"]

    # capacity=100, rate=50/s. 동시 200 요청 → 100개만 통과해야 함
    async def hit():
        r = await client.get(
            f"/{code}",
            headers={"x-api-key": "race-test"},
            follow_redirects=False,
        )
        return r.status_code

    results = await asyncio.gather(*[hit() for _ in range(200)])
    passed = sum(1 for s in results if s == 302)
    denied = sum(1 for s in results if s == 429)

    # asyncio.gather는 사실상 동시 — 거의 모든 요청이 refill 전에 도착
    # 100±5 통과를 기대 (Lua atomic이면 정확히 100, 비atomic이면 200개 모두 통과)
    print(f"\n[race demo] passed={passed}, denied={denied}")
    assert 95 <= passed <= 110, f"passed={passed} — atomic 위반 가능성"
    assert passed + denied == 200


@pytest.mark.asyncio
async def test_identity_isolation(client):
    """다른 API key는 별도 bucket."""
    create = await client.post("/shorten", json={"url": "https://example.com"})
    code = create.json()["code"]

    # user-a로 capacity 소진
    for _ in range(100):
        await client.get(f"/{code}", headers={"x-api-key": "user-a"}, follow_redirects=False)

    # user-b는 fresh
    r = await client.get(f"/{code}", headers={"x-api-key": "user-b"}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["x-ratelimit-remaining"] == "99"
