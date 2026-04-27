#!/usr/bin/env bash
# End-to-end demo: agent-a asks agent-b to download two clips, then queries status.
# Both agents are real `claude -p` (headless Claude Code) sessions.
#
# Pre-reqs: yt-dlp installed; logged-in `claude` CLI; ports 9001/9002 free.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

URL1="https://samplelib.com/lib/preview/mp4/sample-5s.mp4"
URL2="https://samplelib.com/lib/preview/mp4/sample-10s.mp4"

log() { printf '\n\033[1;36m[demo]\033[0m %s\n' "$*"; }

cleanup() {
    log "tearing down"
    [ -f /tmp/a2a-worker.pid ] && kill "$(cat /tmp/a2a-worker.pid)" 2>/dev/null || true
    rm -f /tmp/a2a-worker.pid
    make down >/dev/null 2>&1 || true
}
trap cleanup EXIT

# 0. fresh state
log "resetting state"
rm -f agent-b/state/queue.json
rm -rf agent-b/downloads
mkdir -p agent-b/downloads agent-b/state

# 1. boot A2A servers
log "starting A2A HTTP servers"
make up >/dev/null
sleep 2

# 2. boot worker
log "starting yt-dlp worker"
nohup agent-b/worker.sh >/tmp/a2a-worker.out 2>&1 &
echo $! > /tmp/a2a-worker.pid
sleep 1

# 3. drive agent-a (one-shot prompt; it sends + polls)
A_PROMPT="$(cat <<EOF
Use the a2a MCP tools to talk to your peer (agent-b on :9002).
Do these three actions in order. After EACH action, poll a2a_get_task
every 2 seconds until the task state is 'completed', then print the
reply text from artifacts[0].parts[0].text. Use the same contextId
across all three so they share one conversation thread.

1. a2a_send text="download $URL1"
2. a2a_send text="download $URL2"
3. a2a_send text="status"

Report each peer reply verbatim. Do not retry on errors. Stop after step 3.
EOF
)"

B_PROMPT="$(cat <<'EOF'
Drain your A2A inbox now.

1. Call a2a_inbox.
2. For each task whose state is 'input-required':
   a. Read text from task.history[0].parts[0].text.
   b. Parse first token: 'download', 'status', or 'cancel'.
   c. For 'download <url> [format <fmt>]': run via Bash:
        python3 /home/oriol/iotgw-ng/a2a/agent-b/queue.py enqueue <url> [--format <fmt>]
   d. For 'status' or 'status <id>': run:
        python3 /home/oriol/iotgw-ng/a2a/agent-b/queue.py status [<id>]
   e. For 'cancel <id>': run:
        python3 /home/oriol/iotgw-ng/a2a/agent-b/queue.py cancel <id>
   f. Capture the JSON stdout. Call a2a_respond with taskId and that JSON as text.
3. After processing every inbox item, exit. Do not loop.
EOF
)"

log "starting agent-a session in background"
( cd agent-a && claude -p "$A_PROMPT" \
    --permission-mode bypassPermissions \
    --output-format stream-json --verbose \
    >/tmp/a2a-agent-a.log 2>&1 ) &
A_PID=$!

# 4. drain B in a polling loop while A runs
log "looping agent-b drainer (max 8 cycles)"
for i in 1 2 3 4 5 6 7 8; do
    sleep 4
    log "  drain cycle $i"
    ( cd agent-b && claude -p "$B_PROMPT" \
        --permission-mode bypassPermissions \
        >>/tmp/a2a-agent-b.log 2>&1 ) || true
    # stop if agent-a has finished and queue has no pending input-required
    if ! kill -0 "$A_PID" 2>/dev/null; then
        log "  agent-a finished, one final drain pass"
        ( cd agent-b && claude -p "$B_PROMPT" \
            --permission-mode bypassPermissions \
            >>/tmp/a2a-agent-b.log 2>&1 ) || true
        break
    fi
done

wait "$A_PID" 2>/dev/null || true

# 5. wait for downloads to finish
log "waiting for queue to drain (max 60s)"
for i in $(seq 1 30); do
    PEND=$(python3 agent-b/queue.py status \
        | python3 -c 'import sys,json;print(sum(1 for j in json.load(sys.stdin)["jobs"] if j["state"] in ("queued","running")))')
    [ "$PEND" = "0" ] && break
    sleep 2
done

# 6. final report
log "FINAL queue state"
python3 agent-b/queue.py status

log "downloads on disk"
ls -la agent-b/downloads/ || true

log "agent-a transcript: /tmp/a2a-agent-a.log"
log "agent-b transcript: /tmp/a2a-agent-b.log"
log "worker log:         agent-b/state/worker.log"
