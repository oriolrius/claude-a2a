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

This is a minimal A2A implementation:
- ✅ Agent Card discovery
- ✅ JSON-RPC 2.0 transport
- ✅ Task lifecycle (`submitted` → `input-required` → `completed` / `canceled`)
- ✅ Text parts + artifacts
- ❌ No streaming (`message/stream` SSE) — polling only
- ❌ No push notifications (`tasks/pushNotificationConfig/*`)
- ❌ No auth — bound to 127.0.0.1

`tasks/respond` is a non-standard helper exposed so a Claude session can complete a task that the peer sent it. In a fully-conforming implementation an agent would process incoming messages autonomously and update its own task state.

## Stop

```bash
make down
```
