# Claude A2A — two Claude Code agents over A2A protocol

Two Claude Code agents in subfolders (`agent-a/`, `agent-b/`) talk to each other using Google's [A2A protocol](https://github.com/google/A2A) (Agent2Agent). The protocol is exposed to each Claude session via an MCP server.

## Architecture

```
                    +------------------+              +------------------+
   Claude Code  --> | MCP server (a2a) | -- HTTP -->  | A2A server :9002 |  agent-b
   (agent-a/)       +------------------+              +------------------+
                              |                                ^
                              v                                |
                    +------------------+              +------------------+
                    | A2A server :9001 | <-- HTTP --  | MCP server (a2a) |
                    +------------------+              +------------------+
                            agent-a                    Claude Code
                                                       (agent-b/)
```

- **A2A server** (`shared/a2a.py`): FastAPI + JSON-RPC 2.0. Implements `message/send`, `tasks/get`, `tasks/cancel`, `tasks/respond`, `tasks/inbox`. Exposes Agent Card at `/.well-known/agent-card.json`.
- **MCP bridge** (`shared/mcp_bridge.py`): stdio MCP server exposing 6 tools to Claude (`a2a_send`, `a2a_get_task`, `a2a_inbox`, `a2a_respond`, …).
- Each agent folder has `.mcp.json` so Claude Code auto-loads its bridge.

## Layout

```
a2a/
├── pyproject.toml         # uv project, deps for both agents
├── Makefile
├── smoke.py               # protocol smoke test
├── shared/
│   ├── a2a.py             # protocol server + client
│   └── mcp_bridge.py      # MCP <-> A2A bridge
├── agent-a/
│   ├── server.py          # A2A HTTP on :9001
│   ├── .mcp.json          # registers MCP bridge for Claude
│   └── CLAUDE.md          # agent-a persona + tool guide
└── agent-b/
    ├── server.py          # A2A HTTP on :9002
    ├── .mcp.json
    └── CLAUDE.md
```

## Run

```bash
cd /home/oriol/iotgw-ng/a2a
uv sync
make up        # starts both A2A HTTP servers in background
make smoke     # sanity check the wire protocol
```

Then open two Claude Code sessions:

```bash
# terminal 1
cd agent-a && claude

# terminal 2
cd agent-b && claude
```

Each Claude has the `a2a` MCP server loaded. Try in agent-a:

> Use `a2a_peer_card` to see who agent-b is, then send "hello" via `a2a_send` and poll the task.

In agent-b:

> Check `a2a_inbox`, then `a2a_respond` to the pending task.

## Protocol notes

A2A subset implemented:
- ✅ Agent Card discovery
- ✅ JSON-RPC 2.0 transport
- ✅ Task lifecycle (`submitted` → `input-required` → `completed` / `canceled`)
- ✅ Text parts + artifacts
- ✅ Streaming via `message/stream` and `tasks/resubscribe` (Server-Sent Events)
- ✅ Push notifications (`tasks/pushNotificationConfig/set` + `/get`, async webhook delivery with optional bearer-style token header)
- ❌ No auth on the JSON-RPC endpoint itself — bound to 127.0.0.1

## Tests

```bash
uv sync
uv run pytest
```

17 tests cover: agent card, message/send, get/cancel/respond, inbox, context continuity, SSE message/stream, SSE resubscribe, error paths for unknown tasks/methods, push config set/get, push webhook delivery on artifact + status events (with token header), no-delivery when push not configured.

Push delivery is verified by spinning up a tiny FastAPI capture server on a free port inside the test and asserting on captured payloads + headers.

`tasks/respond` is a non-standard helper exposed so a Claude session can complete a task that the peer sent it. In a fully-conforming implementation an agent would process incoming messages autonomously and update its own task state.

## Stop

```bash
make down
```

## Demo: yt-dlp use case

Concrete demo where agent-a asks agent-b to download videos. Agent-b owns a serial download queue powered by yt-dlp. See [demo/README.md](demo/README.md). Run:

```bash
./demo/run.sh
```
