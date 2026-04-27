"""Smoke test: verify A2A wire format between two running servers.

Run after `make up`.
"""
import asyncio

from shared.a2a import A2AClient


async def main() -> None:
    a = A2AClient("http://127.0.0.1:9001")
    b = A2AClient("http://127.0.0.1:9002")

    print("== peer cards ==")
    print("A:", (await a.get_card())["name"])
    print("B:", (await b.get_card())["name"])

    print("\n== A sends to B ==")
    task = await b.send_message("hello from A")
    tid = task["id"]
    print("created task on B:", tid, "state:", task["status"]["state"])

    print("\n== B inbox ==")
    print(await b.inbox())

    print("\n== B responds ==")
    done = await b.respond(tid, "hi A, this is B")
    print("state:", done["status"]["state"])
    print("artifacts:", done["artifacts"])

    print("\n== A polls B for the task ==")
    print(await b.get_task(tid))

    await a.aclose()
    await b.aclose()


if __name__ == "__main__":
    asyncio.run(main())
