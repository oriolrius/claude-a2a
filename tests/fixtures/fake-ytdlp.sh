#!/usr/bin/env bash
# Test fake of yt-dlp. Honors -o / --print after_move:filepath.
# Creates a tiny file at the templated path and prints it.
set -eu

OUT=""
PRINT_PATH=0
URL=""
while [ $# -gt 0 ]; do
    case "$1" in
        -o) OUT="$2"; shift 2 ;;
        --print) [ "$2" = "after_move:filepath" ] && PRINT_PATH=1; shift 2 ;;
        --) shift; URL="$1"; shift ;;
        --no-progress|--no-warnings|--no-playlist) shift ;;
        -f) shift 2 ;;
        *) URL="$1"; shift ;;
    esac
done

# Replace yt-dlp templates with deterministic values
NAME="$(echo "$URL" | sed 's|.*/||;s|\.[^.]*$||')"
ID="$(echo "$URL" | md5sum | cut -c1-8)"
EXT="mp4"
RESOLVED="$(echo "$OUT" \
    | sed "s|%(title)\.80s|$NAME|;s|%(title)s|$NAME|;s|%(id)s|$ID|;s|%(ext)s|$EXT|")"
mkdir -p "$(dirname "$RESOLVED")"
printf 'fake-content for %s\n' "$URL" > "$RESOLVED"
[ "$PRINT_PATH" = "1" ] && echo "$RESOLVED"
exit 0
