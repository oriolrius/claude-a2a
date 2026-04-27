"""Push notifications: webhook config + delivery."""
import asyncio
import socket

import pytest
from fastapi import FastAPI, Request
import uvicorn


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class CaptureServer:
    """Tiny webhook receiver, runs on free port."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.headers: list[dict] = []
        self.app = FastAPI()

        @self.app.post("/hook")
        async def hook(req: Request) -> dict:
            self.events.append(await req.json())
            self.headers.append(dict(req.headers))
            return {"ok": True}

    async def __aenter__(self) -> "CaptureServer":
        self.port = _free_port()
        config = uvicorn.Config(self.app, host="127.0.0.1", port=self.port,
                                log_level="error")
        self.server = uvicorn.Server(config)
        self._task = asyncio.create_task(self.server.serve())
        for _ in range(50):
            if self.server.started:
                break
            await asyncio.sleep(0.05)
        self.url = f"http://127.0.0.1:{self.port}/hook"
        return self

    async def __aexit__(self, *exc) -> None:
        self.server.should_exit = True
        await self._task


async def test_set_and_get_push_config(client) -> None:
    task = await client.send_message("p")
    res = await client.set_push_config(task["id"], "http://x/hook", token="t1")
    assert res["pushNotificationConfig"]["url"] == "http://x/hook"

    got = await client.get_push_config(task["id"])
    assert got["pushNotificationConfig"]["token"] == "t1"


async def test_push_config_unknown_task(client) -> None:
    with pytest.raises(RuntimeError):
        await client.set_push_config("nope", "http://x")
    with pytest.raises(RuntimeError):
        await client.get_push_config("nope")


async def test_push_delivers_on_state_changes(live_client) -> None:
    client, _ = live_client
    async with CaptureServer() as cap:
        task = await client.send_message("p")
        await client.set_push_config(task["id"], cap.url, token="secret")

        # mutate task — fires artifact-update + status-update final
        await client.respond(task["id"], "hi")

        # wait for deliveries
        for _ in range(50):
            if len(cap.events) >= 2:
                break
            await asyncio.sleep(0.05)

        kinds = [e["kind"] for e in cap.events]
        assert "artifact-update" in kinds
        assert any(e["kind"] == "status-update" and e.get("final") for e in cap.events)
        # token surfaced as header
        assert all(h.get("x-a2a-notification-token") == "secret" for h in cap.headers)


async def test_push_skips_unconfigured_tasks(live_client) -> None:
    client, _ = live_client
    async with CaptureServer() as cap:
        task = await client.send_message("p")
        # do NOT set push config
        await client.respond(task["id"], "x")
        await asyncio.sleep(0.2)
        assert cap.events == []
