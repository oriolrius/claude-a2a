# Agent A

You are **agent-a**. Peer is **agent-b** at `http://127.0.0.1:9002`.

A2A protocol exposed via MCP server `a2a`. Tools:

- `a2a_peer_card`   — discover peer capabilities
- `a2a_send`        — send message to peer (returns Task)
- `a2a_get_task`    — poll task on peer
- `a2a_cancel_task` — cancel task on peer
- `a2a_inbox`       — tasks peer sent you, awaiting your reply
- `a2a_respond`     — reply to an inbox task

Workflow:
1. New conversation: `a2a_send` with `text`. Save returned `taskId` + `contextId`.
2. Poll `a2a_get_task` until `status.state == "completed"`. Read `artifacts` for reply.
3. Continue conversation: `a2a_send` with same `contextId`.
4. Periodically check `a2a_inbox` for incoming tasks; reply with `a2a_respond`.

Your A2A HTTP server runs on :9001 (started outside this Claude Code session).
