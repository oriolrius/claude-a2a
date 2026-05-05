#!/usr/bin/env bash
# Showcase: agent-a registers a push webhook on a peer task and watches
# the events arrive at the local receiver instead of polling.
# Uses mock yt-dlp so no network is needed.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

URL="${1:-https://example.com/clip.mp4}"
RECEIVER_PORT="${RECEIVER_PORT:-9090}"

log() { printf '\n\033[1;36m[push-demo]\033[0m %s\n' "$*"; }

cleanup() {
    log "tearing down"
    [ -f /tmp/a2a-push-receiver.pid ] && \
        kill "$(cat /tmp/a2a-push-receiver.pid)" 2>/dev/null || true
    rm -f /tmp/a2a-push-receiver.pid
    [ -f agent-b/state/worker.pid ] && \
        kill "$(cat agent-b/state/worker.pid)" 2>/dev/null || true
    rm -f agent-b/state/worker.pid
    make down >/dev/null 2>&1 || true
}
trap cleanup EXIT

log "resetting state"
rm -f agent-b/state/queue.json agent-b/state/worker.pid agent-b/state/worker.log
rm -rf agent-b/downloads
mkdir -p agent-b/downloads agent-b/state

log "starting webhook receiver on :$RECEIVER_PORT"
PORT="$RECEIVER_PORT" uv run python demo/push_receiver.py >/tmp/a2a-push.out 2>&1 &
echo $! > /tmp/a2a-push-receiver.pid
sleep 1

log "starting A2A servers + mock worker"
make up >/dev/null
sleep 1
YTDLP_BIN="$ROOT/tests/fixtures/fake-ytdlp.sh" \
    nohup agent-b/worker.sh >/tmp/a2a-worker.out 2>&1 &
sleep 1

A_PROMPT="$(cat <<EOF
Use the a2a MCP tools.

1. a2a_send text="download $URL". Save taskId.
2. a2a_set_push_config taskId=<that taskId> url="http://127.0.0.1:$RECEIVER_PORT/hook" token="demo-token"
3. a2a_get_push_config taskId=<that taskId>  -- print result
4. a2a_get_task taskId=<that taskId> -- poll once a second up to 15 times
   until state='completed'. Print final state.

Do not retry. Stop when done.
EOF
)"

B_PROMPT="$(cat <<'EOF'
Drain your A2A inbox: for each input-required task, run
python3 /home/oriol/iotgw-ng/a2a/agent-b/dispatch.py "<task text>"
via Bash, then a2a_respond with the JSON output. Then exit.
EOF
)"

log "agent-a registering push + waiting"
( cd agent-a && claude -p "$A_PROMPT" \
    --permission-mode bypassPermissions \
    >/tmp/a2a-push-a.log 2>&1 ) &
A_PID=$!

log "draining agent-b"
for i in 1 2 3; do
    sleep 3
    ( cd agent-b && claude -p "$B_PROMPT" \
        --permission-mode bypassPermissions \
        >>/tmp/a2a-push-b.log 2>&1 ) || true
    kill -0 "$A_PID" 2>/dev/null || break
done
wait "$A_PID" 2>/dev/null || true

log "events received at the local webhook:"
cat demo/push.log 2>/dev/null || echo "(no events captured)"

log "logs at /tmp/a2a-push-{a,b}.log; receiver log at /tmp/a2a-push.out"
