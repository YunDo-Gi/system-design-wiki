import pytest


@pytest.mark.asyncio
async def test_free_tier_limited_at_10(client):
    """X-User-Tier: free (또는 미선언) → endpoint default = 10."""
    statuses = []
    for _ in range(11):
        r = await client.post(
            "/shorten",
            json={"url": "https://example.com"},
            headers={"x-api-key": "free-tier-test", "x-user-tier": "free"},
        )
        statuses.append(r.status_code)
    passed = sum(1 for s in statuses if s == 200)
    denied = sum(1 for s in statuses if s == 429)
    assert passed == 10
    assert denied == 1


@pytest.mark.asyncio
async def test_premium_tier_limited_at_50(client):
    """premium tier → 50까지 통과."""
    statuses = []
    for _ in range(51):
        r = await client.post(
            "/shorten",
            json={"url": "https://example.com"},
            headers={"x-api-key": "premium-tier-test", "x-user-tier": "premium"},
        )
        statuses.append(r.status_code)
    passed = sum(1 for s in statuses if s == 200)
    denied = sum(1 for s in statuses if s == 429)
    assert passed == 50
    assert denied == 1


@pytest.mark.asyncio
async def test_default_tier_uses_endpoint_default(client):
    """tier 헤더 없으면 endpoint default = 10."""
    statuses = []
    for _ in range(11):
        r = await client.post(
            "/shorten",
            json={"url": "https://example.com"},
            headers={"x-api-key": "default-tier-test"},
        )
        statuses.append(r.status_code)
    passed = sum(1 for s in statuses if s == 200)
    denied = sum(1 for s in statuses if s == 429)
    assert passed == 10
    assert denied == 1
