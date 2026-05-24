import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client():
    from app.main import app

    # httpx ASGITransport doesn't run lifespan automatically.
    # Drive it manually so app.state.rules is populated.
    async with LifespanContext(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


class LifespanContext:
    """Minimal ASGI lifespan driver — startup on enter, shutdown on exit."""

    def __init__(self, app):
        self.app = app
        self._receive_queue = None
        self._send_queue = None
        self._task = None

    async def __aenter__(self):
        import asyncio

        self._receive_queue = asyncio.Queue()
        self._send_queue = asyncio.Queue()

        async def receive():
            return await self._receive_queue.get()

        async def send(message):
            await self._send_queue.put(message)

        self._task = asyncio.create_task(
            self.app({"type": "lifespan"}, receive, send)
        )
        await self._receive_queue.put({"type": "lifespan.startup"})
        msg = await self._send_queue.get()
        assert msg["type"] == "lifespan.startup.complete", msg
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self._receive_queue.put({"type": "lifespan.shutdown"})
        msg = await self._send_queue.get()
        assert msg["type"] == "lifespan.shutdown.complete", msg
        await self._task
