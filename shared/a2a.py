"""Minimal A2A protocol implementation (Google Agent2Agent spec subset).

Implements:
- Agent Card discovery at /.well-known/agent-card.json
- JSON-RPC 2.0 endpoint at / supporting:
    message/send         — submit a message, returns a Task
    tasks/get            — fetch task by id
    tasks/cancel         — cancel a task
    tasks/respond        — non-standard helper: agent completes an input-required task

Task lifecycle states: submitted, working, input-required, completed, canceled, failed.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

TaskState = Literal[
    "submitted", "working", "input-required",
    "completed", "canceled", "failed", "rejected",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TextPart(BaseModel):
    kind: Literal["text"] = "text"
    text: str


class Message(BaseModel):
    role: Literal["user", "agent"]
    parts: list[TextPart]
    messageId: str = Field(default_factory=lambda: str(uuid.uuid4()))
    taskId: str | None = None
    contextId: str | None = None


class TaskStatus(BaseModel):
    state: TaskState
    message: Message | None = None
    timestamp: str = Field(default_factory=now_iso)


class Artifact(BaseModel):
    artifactId: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str | None = None
    parts: list[TextPart]


class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    contextId: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: TaskStatus
    history: list[Message] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    kind: Literal["task"] = "task"


class AgentCard(BaseModel):
    name: str
    description: str
    version: str = "0.1.0"
    url: str
    protocolVersion: str = "0.2.0"
    capabilities: dict[str, Any] = Field(default_factory=lambda: {"streaming": False})
    defaultInputModes: list[str] = Field(default_factory=lambda: ["text/plain"])
    defaultOutputModes: list[str] = Field(default_factory=lambda: ["text/plain"])
    skills: list[dict[str, Any]] = Field(default_factory=list)


class TaskStore:
    """In-memory store. Tasks indexed by id. Inbox = tasks awaiting local agent reply."""

    def __init__(self) -> None:
        self.tasks: dict[str, Task] = {}

    def create_from_message(self, msg: Message) -> Task:
        msg.taskId = msg.taskId or str(uuid.uuid4())
        msg.contextId = msg.contextId or str(uuid.uuid4())
        task = Task(
            id=msg.taskId,
            contextId=msg.contextId,
            status=TaskStatus(state="input-required"),
            history=[msg],
        )
        self.tasks[task.id] = task
        return task

    def get(self, task_id: str) -> Task | None:
        return self.tasks.get(task_id)

    def cancel(self, task_id: str) -> Task | None:
        t = self.tasks.get(task_id)
        if t and t.status.state not in ("completed", "canceled", "failed"):
            t.status = TaskStatus(state="canceled")
        return t

    def respond(self, task_id: str, text: str) -> Task | None:
        t = self.tasks.get(task_id)
        if not t:
            return None
        reply = Message(role="agent", parts=[TextPart(text=text)],
                        taskId=t.id, contextId=t.contextId)
        t.history.append(reply)
        t.artifacts.append(Artifact(name="response", parts=[TextPart(text=text)]))
        t.status = TaskStatus(state="completed", message=reply)
        return t

    def inbox(self) -> list[Task]:
        return [t for t in self.tasks.values() if t.status.state == "input-required"]


# ---------- JSON-RPC server ----------

def make_app(card: AgentCard, store: TaskStore) -> FastAPI:
    app = FastAPI(title=card.name)

    @app.get("/.well-known/agent-card.json")
    def agent_card() -> dict[str, Any]:
        return card.model_dump()

    @app.post("/")
    async def jsonrpc(req: Request) -> JSONResponse:
        body = await req.json()
        rpc_id = body.get("id")
        method = body.get("method")
        params = body.get("params") or {}

        def ok(result: Any) -> JSONResponse:
            return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": result})

        def err(code: int, message: str) -> JSONResponse:
            return JSONResponse(
                {"jsonrpc": "2.0", "id": rpc_id,
                 "error": {"code": code, "message": message}},
            )

        if method == "message/send":
            msg = Message(**params["message"])
            task = store.create_from_message(msg)
            return ok(task.model_dump())

        if method == "tasks/get":
            t = store.get(params["id"])
            return ok(t.model_dump()) if t else err(-32001, "Task not found")

        if method == "tasks/cancel":
            t = store.cancel(params["id"])
            return ok(t.model_dump()) if t else err(-32001, "Task not found")

        if method == "tasks/respond":
            t = store.respond(params["id"], params["text"])
            return ok(t.model_dump()) if t else err(-32001, "Task not found")

        if method == "tasks/inbox":
            return ok([t.model_dump() for t in store.inbox()])

        return err(-32601, f"Method not found: {method}")

    return app


# ---------- A2A client ----------

class A2AClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(timeout=30.0)

    async def get_card(self) -> dict[str, Any]:
        r = await self._http.get(f"{self.base_url}/.well-known/agent-card.json")
        r.raise_for_status()
        return r.json()

    async def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = {"jsonrpc": "2.0", "id": str(uuid.uuid4()),
                   "method": method, "params": params}
        r = await self._http.post(self.base_url + "/", json=payload)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise RuntimeError(data["error"])
        return data["result"]

    async def send_message(self, text: str, context_id: str | None = None) -> dict[str, Any]:
        msg = Message(role="user", parts=[TextPart(text=text)], contextId=context_id)
        return await self._rpc("message/send", {"message": msg.model_dump()})

    async def get_task(self, task_id: str) -> dict[str, Any]:
        return await self._rpc("tasks/get", {"id": task_id})

    async def cancel_task(self, task_id: str) -> dict[str, Any]:
        return await self._rpc("tasks/cancel", {"id": task_id})

    async def respond(self, task_id: str, text: str) -> dict[str, Any]:
        return await self._rpc("tasks/respond", {"id": task_id, "text": text})

    async def inbox(self) -> list[dict[str, Any]]:
        return await self._rpc("tasks/inbox", {})

    async def aclose(self) -> None:
        await self._http.aclose()


async def run_server(app: FastAPI, host: str, port: int) -> None:
    import uvicorn
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


def serve_blocking(app: FastAPI, host: str, port: int) -> None:
    asyncio.run(run_server(app, host, port))
