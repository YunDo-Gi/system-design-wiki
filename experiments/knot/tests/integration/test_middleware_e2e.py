import pytest


@pytest.mark.asyncio
async def test_shorten_returns_200_with_rate_limit_headers(client):
    response = await client.post("/shorten", json={"url": "https://example.com"})
    assert response.status_code == 200
    assert response.headers["x-ratelimit-limit"] == "10"
    assert response.headers["x-ratelimit-remaining"] == "10"
    assert "x-ratelimit-retry-after" not in response.headers


@pytest.mark.asyncio
async def test_redirect_returns_302_with_rate_limit_headers(client):
    create = await client.post("/shorten", json={"url": "https://example.com"})
    code = create.json()["code"]
    response = await client.get(f"/{code}", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["x-ratelimit-limit"] == "50"


@pytest.mark.asyncio
async def test_unknown_endpoint_still_passes(client):
    response = await client.get("/healthz")
    assert response.status_code == 200
