#!/usr/bin/env bash
# Showcase: agent-a uses a2a_stream (SSE) to receive task events live
# instead of polling. Uses mock yt-dlp so it runs without network.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

URL="${1:-https://example.com/clip.mp4}"

log() { printf '\n\033[1;36m[stream-demo]\033[0m %s\n' "$*"; }

cleanup() {
    log "tearing down"
    [ -f agent-b/state/worker.pid ] && \
        kill "$(cat agent-b/state/worker.pid)" 2>/dev/null || true
    rm -f agent-b/state/worker.pid
    make down >/dev/null 2>&1 || true
}
trap cleanup EXIT

log "resetting state, starting servers + mock worker"
rm -f agent-b/state/queue.json agent-b/state/worker.pid agent-b/state/worker.log
rm -rf agent-b/downloads
mkdir -p agent-b/downloads agent-b/state
make up >/dev/null
YTDLP_BIN="$ROOT/tests/fixtures/fake-ytdlp.sh" \
    nohup agent-b/worker.sh >/tmp/a2a-worker.out 2>&1 &
sleep 1

A_PROMPT="$(cat <<EOF
Use a2a_stream (NOT a2a_send + poll) to send the message
"download $URL" to your peer with timeoutSec=20. The tool returns a
list of SSE events. Print every event in order with its 'kind' and key
fields. Watch for kind='task', kind='artifact-update', and the final
kind='status-update' with state='completed'. Then stop.
EOF
)"

B_PROMPT="$(cat <<'EOF'
Drain your A2A inbox: for each input-required task, run
python3 /home/oriol/iotgw-ng/a2a/agent-b/dispatch.py "<task text>"
via Bash, then a2a_respond with the JSON output. Then exit.
EOF
)"

log "agent-a streaming"
( cd agent-a && claude -p "$A_PROMPT" \
    --permission-mode bypassPermissions \
    >/tmp/a2a-stream-a.log 2>&1 ) &
A_PID=$!

log "draining agent-b (3 cycles)"
for i in 1 2 3; do
    sleep 3
    ( cd agent-b && claude -p "$B_PROMPT" \
        --permission-mode bypassPermissions \
        >>/tmp/a2a-stream-b.log 2>&1 ) || true
    kill -0 "$A_PID" 2>/dev/null || break
done
wait "$A_PID" 2>/dev/null || true

log "agent-a saw these SSE events (grep from transcript)"
grep -E '"kind":"(task|artifact-update|status-update)"' /tmp/a2a-stream-a.log | head -20 || true
log "logs at /tmp/a2a-stream-{a,b}.log"
