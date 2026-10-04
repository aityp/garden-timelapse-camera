#!/usr/bin/env bash
#
# One command to SEE the time-lapse so far, without pulling any frames.
#
# Builds a small preview on the Pi (straight off the SD card), copies just that
# MP4 back, and opens it. Nothing touches the archive drive, and the drive does
# not even need to be plugged in.
#
# Usage (on the Mac):
#   ./quicklook.sh                    # today
#   ./quicklook.sh 2026-08-01
#   ./quicklook.sh 2026-08-01 2026-08-02
#   ./quicklook.sh 2026-08-01 2026-08-02 4    # every 4th frame, much faster
#
# For the real edit master use make-timelapse.sh instead, which needs the
# frames pulled to the drive first.
#
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
[ -f "$HERE/config.sh" ] || { echo "No config.sh next to this script - copy config.example.sh to config.sh and edit it." >&2; exit 1; }
source "$HERE/config.sh"

# The project folder on the Pi, where preview.sh lives. Change this one line if
# you named your Pi folder something other than garden-cam.
PI_PROJECT="garden-cam"

START="${1:-$(date +%F)}"
END="${2:-$START}"
STEP="${3:-1}"

echo "Building preview on the Pi ($START to $END, every ${STEP} frame(s))..."
REMOTE=$(ssh "$PI" "~/$PI_PROJECT/preview.sh '$START' '$END' '$STEP'" | tail -1)

LOCAL="/tmp/$(basename "$REMOTE")"
scp -q "$PI:$REMOTE" "$LOCAL"
ssh "$PI" "rm -f '$REMOTE'"          # don't leave previews filling the card

echo "$LOCAL  ($(du -h "$LOCAL" | cut -f1))"
open "$LOCAL"
