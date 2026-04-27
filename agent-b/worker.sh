#!/usr/bin/env bash
# Serial yt-dlp worker. Polls queue.py for next job, downloads it,
# updates state. Loops forever until SIGTERM/SIGINT.
#
# Env overrides:
#   YTDLP_BIN     binary to invoke (default: yt-dlp)
#   QUEUE_DIR     directory containing queue.py (default: this script's dir)
#   DOWNLOAD_DIR  output dir   (default: $QUEUE_DIR/downloads)
#   STATE_DIR     state dir    (default: $QUEUE_DIR/state)
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
QUEUE_DIR="${QUEUE_DIR:-$HERE}"
DOWNLOAD_DIR="${DOWNLOAD_DIR:-$QUEUE_DIR/downloads}"
STATE_DIR="${STATE_DIR:-$QUEUE_DIR/state}"
YTDLP_BIN="${YTDLP_BIN:-yt-dlp}"

mkdir -p "$DOWNLOAD_DIR" "$STATE_DIR"
LOG="$STATE_DIR/worker.log"
PID_FILE="$STATE_DIR/worker.pid"

echo $$ > "$PID_FILE"
RUNNING=1
on_term() { RUNNING=0; }
trap on_term SIGTERM SIGINT

echo "[worker] start pid=$$ ytdlp=$YTDLP_BIN download_dir=$DOWNLOAD_DIR" | tee -a "$LOG"

cleanup() {
    rm -f "$PID_FILE"
    echo "[worker] stop pid=$$" | tee -a "$LOG"
}
trap cleanup EXIT

while [ "$RUNNING" = "1" ]; do
    JOB="$(python3 "$QUEUE_DIR/queue.py" next)"
    if [ -z "$JOB" ]; then
        sleep 1
        continue
    fi
    ID="$(echo "$JOB" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')"
    URL="$(echo "$JOB" | python3 -c 'import sys,json;print(json.load(sys.stdin)["url"])')"
    FMT="$(echo "$JOB" | python3 -c 'import sys,json;j=json.load(sys.stdin);print(j["format"] or "")')"

    echo "[worker] $(date -Iseconds) job=$ID url=$URL fmt=${FMT:-default}" | tee -a "$LOG"

    OUT_TMPL="$DOWNLOAD_DIR/%(title).80s [%(id)s].%(ext)s"
    YTDLP_ARGS=(--no-progress --no-warnings --no-playlist
                -f "${FMT:-best[height<=480]/best}"
                -o "$OUT_TMPL"
                --print "after_move:filepath")

    if FILE="$("$YTDLP_BIN" "${YTDLP_ARGS[@]}" -- "$URL" 2>>"$LOG")"; then
        FILE="$(echo "$FILE" | tail -n1)"
        python3 "$QUEUE_DIR/queue.py" mark "$ID" done --file "$FILE" --progress 100 >/dev/null
        echo "[worker] done $ID -> $FILE" | tee -a "$LOG"
    else
        python3 "$QUEUE_DIR/queue.py" mark "$ID" failed --error "yt-dlp exited non-zero" >/dev/null
        echo "[worker] FAILED $ID" | tee -a "$LOG"
    fi
done
