"""MCP server bridging Claude Code <-> A2A.

Two A2A endpoints:
  - PEER : remote agent we send messages to
  - LOCAL: our own A2A server (queried for inbox + respond on tasks others sent us)

Tools exposed to Claude:
  a2a_peer_card     -> peer's Agent Card
  a2a_send          -> send message to peer (creates Task on peer)
  a2a_get_task      -> poll a task on peer
  a2a_cancel_task   -> cancel a task on peer
  a2a_inbox         -> list tasks awaiting reply on local server
  a2a_respond       -> complete an inbox task with a text reply
"""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from shared.a2a import A2AClient


def build_server(name: str, peer_url: str, local_url: str) -> Server:
    server: Server = Server(name)
    peer = A2AClient(peer_url)
    local = A2AClient(local_url)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(name="a2a_peer_card",
                 description="Fetch peer agent's A2A Agent Card.",
                 inputSchema={"type": "object", "properties": {}}),
            Tool(name="a2a_send",
                 description="Send a text message to peer. Returns Task object.",
                 inputSchema={
                     "type": "object",
                     "properties": {
                         "text": {"type": "string"},
                         "contextId": {"type": "string"},
                     },
                     "required": ["text"],
                 }),
            Tool(name="a2a_get_task",
                 description="Get task state from peer (poll for completion).",
                 inputSchema={
                     "type": "object",
                     "properties": {"taskId": {"type": "string"}},
                     "required": ["taskId"],
                 }),
            Tool(name="a2a_cancel_task",
                 description="Cancel a task on peer.",
                 inputSchema={
                     "type": "object",
                     "properties": {"taskId": {"type": "string"}},
                     "required": ["taskId"],
                 }),
            Tool(name="a2a_inbox",
                 description="List tasks the peer sent ME awaiting my reply.",
                 inputSchema={"type": "object", "properties": {}}),
            Tool(name="a2a_respond",
                 description="Reply to an inbox task; marks it completed.",
                 inputSchema={
                     "type": "object",
                     "properties": {
                         "taskId": {"type": "string"},
                         "text": {"type": "string"},
                     },
                     "required": ["taskId", "text"],
                 }),
        ]

    def _text(payload: Any) -> list[TextContent]:
        return [TextContent(type="text", text=json.dumps(payload, indent=2, default=str))]

    @server.call_tool()
    async def call_tool(tool: str, args: dict[str, Any]) -> list[TextContent]:
        try:
            if tool == "a2a_peer_card":
                return _text(await peer.get_card())
            if tool == "a2a_send":
                return _text(await peer.send_message(args["text"], args.get("contextId")))
            if tool == "a2a_get_task":
                return _text(await peer.get_task(args["taskId"]))
            if tool == "a2a_cancel_task":
                return _text(await peer.cancel_task(args["taskId"]))
            if tool == "a2a_inbox":
                return _text(await local.inbox())
            if tool == "a2a_respond":
                return _text(await local.respond(args["taskId"], args["text"]))
        except Exception as e:
            return _text({"error": str(e)})
        raise ValueError(f"unknown tool: {tool}")

    return server


async def _run(server: Server) -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    # CLI: mcp_bridge.py <name> <peer_url> <local_url>
    name, peer_url, local_url = sys.argv[1], sys.argv[2], sys.argv[3]
    asyncio.run(_run(build_server(name, peer_url, local_url)))


if __name__ == "__main__":
    main()
