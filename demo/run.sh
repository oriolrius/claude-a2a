#!/usr/bin/env bash
# End-to-end demo: agent-a asks agent-b to download videos.
# Both agents are real `claude -p` (headless Claude Code) sessions.
#
# Usage: ./demo/run.sh [URL ...] [--mock-ytdlp] [--rounds N]
#
# With no URLs, defaults to two short clips from samplelib.com.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

URLS=()
MOCK=0
ROUNDS=
while [ $# -gt 0 ]; do
    case "$1" in
        --mock-ytdlp) MOCK=1; shift ;;
        --rounds) ROUNDS="$2"; shift 2 ;;
        -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
        *) URLS+=("$1"); shift ;;
    esac
done
if [ "${#URLS[@]}" -eq 0 ]; then
    URLS=("https://samplelib.com/lib/preview/mp4/sample-5s.mp4"
          "https://samplelib.com/lib/preview/mp4/sample-10s.mp4")
fi
# Default rounds = one drain per URL + one for the final 'status' send
[ -z "$ROUNDS" ] && ROUNDS=$(( ${#URLS[@]} + 1 ))

log() { printf '\n\033[1;36m[demo]\033[0m %s\n' "$*"; }

cleanup() {
    log "tearing down"
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

log "starting A2A HTTP servers"
make up >/dev/null
sleep 2

log "starting yt-dlp worker (mock=$MOCK)"
if [ "$MOCK" = "1" ]; then
    YTDLP_BIN="$ROOT/tests/fixtures/fake-ytdlp.sh" \
        nohup agent-b/worker.sh >/tmp/a2a-worker.out 2>&1 &
else
    nohup agent-b/worker.sh >/tmp/a2a-worker.out 2>&1 &
fi
sleep 1

# Build send-then-poll instructions for agent-a
A_STEPS=""
i=1
for u in "${URLS[@]}"; do
    A_STEPS+="$i. a2a_send text=\"download $u\"
"
    i=$((i+1))
done
A_STEPS+="$i. a2a_send text=\"status\""

A_PROMPT="$(cat <<EOF
Use the a2a MCP tools to talk to your peer (agent-b on :9002).
Do these actions in order. After EACH a2a_send, poll a2a_get_task every
2 seconds until the task state is 'completed', then print the reply text
from artifacts[0].parts[0].text. Use the same contextId across all sends
so they share one conversation thread.

$A_STEPS

Report each peer reply verbatim. Stop after the final step.
EOF
)"

B_PROMPT="$(cat <<'EOF'
Drain your A2A inbox now.

1. Call a2a_inbox.
2. For each task whose state is 'input-required':
   a. Read the message text from task.history[0].parts[0].text.
   b. Run via Bash: python3 /home/oriol/iotgw-ng/a2a/agent-b/dispatch.py "<that text>"
   c. Take the JSON stdout and call a2a_respond with the taskId and that JSON as the reply text.
3. After processing every inbox item, exit. Do not loop.
EOF
)"

log "starting agent-a session in background"
( cd agent-a && claude -p "$A_PROMPT" \
    --permission-mode bypassPermissions \
    --output-format stream-json --verbose \
    >/tmp/a2a-agent-a.log 2>&1 ) &
A_PID=$!

log "looping agent-b drainer (max $ROUNDS cycles)"
for i in $(seq 1 "$ROUNDS"); do
    sleep 4
    log "  drain cycle $i/$ROUNDS"
    ( cd agent-b && claude -p "$B_PROMPT" \
        --permission-mode bypassPermissions \
        >>/tmp/a2a-agent-b.log 2>&1 ) || true
    if ! kill -0 "$A_PID" 2>/dev/null; then
        log "  agent-a finished, one final drain pass"
        ( cd agent-b && claude -p "$B_PROMPT" \
            --permission-mode bypassPermissions \
            >>/tmp/a2a-agent-b.log 2>&1 ) || true
        break
    fi
done

wait "$A_PID" 2>/dev/null || true

log "waiting for queue to drain (max 60s)"
for i in $(seq 1 30); do
    PEND=$(python3 agent-b/queue.py status \
        | python3 -c 'import sys,json;print(sum(1 for j in json.load(sys.stdin)["jobs"] if j["state"] in ("queued","running")))')
    [ "$PEND" = "0" ] && break
    sleep 2
done

log "FINAL queue state"
python3 agent-b/queue.py status

log "downloads on disk"
ls -la agent-b/downloads/ || true

log "logs:"
echo "  agent-a transcript : /tmp/a2a-agent-a.log"
echo "  agent-b transcripts: /tmp/a2a-agent-b.log"
echo "  worker             : agent-b/state/worker.log"
