"""Test fixtures: in-process A2A server via httpx ASGI transport (no real network)."""
from __future__ import annotations

import asyncio
import socket
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
import uvicorn

from shared.a2a import A2AClient, AgentCard, TaskStore, make_app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest_asyncio.fixture
async def store() -> TaskStore:
    s = TaskStore()
    yield s
    await s.aclose()


@pytest_asyncio.fixture
async def app(store: TaskStore):
    card = AgentCard(name="test-agent", description="t", url="http://test")
    return make_app(card, store)


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[A2AClient]:
    """ASGI-transport client: in-process, no socket. Used for non-streaming tests."""
    transport = httpx.ASGITransport(app=app)
    http = httpx.AsyncClient(transport=transport, base_url="http://test")
    c = A2AClient("http://test", http=http)
    yield c
    await http.aclose()


@asynccontextmanager
async def _serve(app, port: int) -> AsyncIterator[None]:
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    # wait until ready
    for _ in range(50):
        if server.started:
            break
        await asyncio.sleep(0.05)
    try:
        yield
    finally:
        server.should_exit = True
        await task


@pytest_asyncio.fixture
async def live_client(app) -> AsyncIterator[tuple[A2AClient, str]]:
    """Real uvicorn server on loopback. Required for SSE streaming tests."""
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    async with _serve(app, port):
        c = A2AClient(base)
        try:
            yield c, base
        finally:
            await c.aclose()
