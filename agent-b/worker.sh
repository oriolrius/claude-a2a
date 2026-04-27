#!/usr/bin/env bash
# Serial yt-dlp worker. Polls queue.py for next job, downloads it,
# updates state. Runs forever until killed.
set -u
cd "$(dirname "$0")"

DOWNLOAD_DIR="$(pwd)/downloads"
mkdir -p "$DOWNLOAD_DIR" state
LOG="state/worker.log"

echo "[worker] starting pid=$$ download_dir=$DOWNLOAD_DIR" | tee -a "$LOG"

while true; do
    JOB="$(python3 queue.py next)"
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

    if FILE="$(yt-dlp "${YTDLP_ARGS[@]}" -- "$URL" 2>>"$LOG")"; then
        FILE="$(echo "$FILE" | tail -n1)"
        python3 queue.py mark "$ID" done --file "$FILE" --progress 100 >/dev/null
        echo "[worker] done $ID -> $FILE" | tee -a "$LOG"
    else
        python3 queue.py mark "$ID" failed --error "yt-dlp exited non-zero" >/dev/null
        echo "[worker] FAILED $ID" | tee -a "$LOG"
    fi
done
