import os

import pytest


@pytest.mark.asyncio
async def test_healthz_reports_redis_ok_when_available(client):
    response = await client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    if os.environ.get("REDIS_AVAILABLE") == "1":
        assert body["redis"] == "ok"
    else:
        assert body["redis"].startswith(("ok", "error"))
