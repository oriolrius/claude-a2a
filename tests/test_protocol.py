"""Core JSON-RPC + non-streaming features."""
import pytest

from shared.a2a import A2AClient, TaskStore


async def test_agent_card(client: A2AClient) -> None:
    card = await client.get_card()
    assert card["name"] == "test-agent"
    assert card["protocolVersion"]
    assert card["capabilities"]["streaming"] is True
    assert card["capabilities"]["pushNotifications"] is True


async def test_send_message_creates_task(client: A2AClient, store: TaskStore) -> None:
    task = await client.send_message("hello")
    assert task["status"]["state"] == "input-required"
    assert task["history"][0]["parts"][0]["text"] == "hello"
    assert task["id"] in store.tasks


async def test_get_task(client: A2AClient) -> None:
    task = await client.send_message("ping")
    fetched = await client.get_task(task["id"])
    assert fetched["id"] == task["id"]


async def test_get_task_not_found(client: A2AClient) -> None:
    with pytest.raises(RuntimeError) as ei:
        await client.get_task("nonexistent")
    assert ei.value.args[0]["code"] == -32001


async def test_unknown_method_returns_error(client: A2AClient) -> None:
    with pytest.raises(RuntimeError) as ei:
        await client._rpc("does/not/exist", {})
    assert ei.value.args[0]["code"] == -32601


async def test_respond_completes_task(client: A2AClient) -> None:
    task = await client.send_message("hi")
    done = await client.respond(task["id"], "world")
    assert done["status"]["state"] == "completed"
    assert done["artifacts"][0]["parts"][0]["text"] == "world"
    assert done["history"][-1]["role"] == "agent"


async def test_cancel_task(client: A2AClient) -> None:
    task = await client.send_message("x")
    canceled = await client.cancel_task(task["id"])
    assert canceled["status"]["state"] == "canceled"


async def test_cancel_after_complete_is_noop(client: A2AClient) -> None:
    task = await client.send_message("x")
    await client.respond(task["id"], "done")
    res = await client.cancel_task(task["id"])
    assert res["status"]["state"] == "completed"


async def test_inbox_lists_pending(client: A2AClient) -> None:
    t1 = await client.send_message("a")
    t2 = await client.send_message("b")
    await client.respond(t2["id"], "answered")

    inbox = await client.inbox()
    ids = [t["id"] for t in inbox]
    assert t1["id"] in ids
    assert t2["id"] not in ids


async def test_context_id_continuity(client: A2AClient) -> None:
    t1 = await client.send_message("first")
    ctx = t1["contextId"]
    t2 = await client.send_message("second", context_id=ctx)
    assert t2["contextId"] == ctx
    assert t2["id"] != t1["id"]
