# yt-dlp demo — two real Claude Code agents over A2A

Use case: **agent-a** asks **agent-b** to download videos. Agent-b is a yt-dlp expert with a serial download queue.

## Pieces

| Piece | What it does |
|------|---|
| `agent-b/queue.py` | JSON-backed FIFO queue (flock-protected). Subcommands: `enqueue`, `status`, `cancel`, `clear-done`, plus worker-internal `next` / `mark`. |
| `agent-b/worker.sh` | Background daemon, pulls next queued job, runs `yt-dlp`, marks done/failed. Serial. |
| `agent-a/CLAUDE.md` | Tells Claude to send plain-text commands (`download <url>`, `status`, `cancel <id>`) via `a2a_send` and poll. |
| `agent-b/CLAUDE.md` | Tells Claude to drain `a2a_inbox`, parse text, run `python3 queue.py …` via Bash, reply with stdout. |
| `demo/run.sh` | Starts servers + worker, drives both Claude sessions headless via `claude -p`, prints final state. |

No second MCP server. Agent-b uses Claude's built-in Bash tool to call `queue.py`.

## Run

```bash
cd a2a
./demo/run.sh
```

Default URLs: two short clips from samplelib.com (~3 MB and ~5 MB).

## What you'll see

1. Servers + worker boot.
2. Agent-a session launches headless, sends three A2A messages: `download <url1>`, `download <url2>`, `status`.
3. Agent-b session is invoked in a poll loop; each pass drains its inbox, calls `queue.py`, replies.
4. Worker downloads each file in order into `agent-b/downloads/`.
5. Final report: queue snapshot + `ls downloads/`.

## Logs

- `/tmp/a2a-agent-a.log` — full agent-a transcript (stream-json)
- `/tmp/a2a-agent-b.log` — agent-b transcripts concatenated across drain cycles
- `agent-b/state/worker.log` — yt-dlp worker output
- `agent-b/state/queue.json` — current queue

## Notes

- Real `claude -p` sessions, real Claude Code subscription quota.
- Permission mode: `bypassPermissions` so the headless sessions don't block on tool prompts. Demo is local-only.
- Worker serial by design (`download in order`). Concurrency would need a small change in `worker.sh`.
- YouTube URLs hit anti-bot checks without cookies; demo uses direct MP4 samples to keep the proof-of-concept clean. yt-dlp still handles them via its generic extractor, exercising the same code path.
