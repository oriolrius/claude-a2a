"""SSE streaming: message/stream + tasks/resubscribe."""
import asyncio


async def test_message_stream_emits_initial_and_final(live_client) -> None:
    client, base = live_client
    events: list[dict] = []
    task_id: str | None = None

    async def consumer() -> None:
        nonlocal task_id
        async for ev in client.stream_message("stream-me"):
            events.append(ev)
            if ev.get("kind") == "task":
                task_id = ev["taskId"]
            if ev.get("kind") == "task" and not ev.get("final"):
                # respond out-of-band to drive task to completion
                await client.respond(ev["taskId"], "answered")

    await asyncio.wait_for(consumer(), timeout=5)

    kinds = [e["kind"] for e in events]
    assert "task" in kinds
    assert "artifact-update" in kinds
    assert any(e["kind"] == "status-update" and e["final"] for e in events)
    final = next(e for e in events if e.get("final"))
    assert final["status"]["state"] == "completed"


async def test_resubscribe_to_existing_task(live_client) -> None:
    client, _ = live_client
    task = await client.send_message("base")

    events: list[dict] = []

    async def listen() -> None:
        async for ev in client.resubscribe(task["id"]):
            events.append(ev)

    listener = asyncio.create_task(listen())
    await asyncio.sleep(0.1)
    await client.respond(task["id"], "late reply")
    await asyncio.wait_for(listener, timeout=5)

    assert any(e["kind"] == "artifact-update" for e in events)
    assert any(e["kind"] == "status-update" and e["final"] for e in events)


async def test_resubscribe_unknown_task_errors(live_client) -> None:
    client, _ = live_client

    async def attempt() -> list:
        return [ev async for ev in client.resubscribe("does-not-exist")]

    # server returns a 200 SSE? Actually JSONResponse with error in code path.
    # client's stream() will raise on non-stream content; expect any exception.
    try:
        await asyncio.wait_for(attempt(), timeout=2)
    except Exception:
        return
    raise AssertionError("expected error for unknown taskId")
