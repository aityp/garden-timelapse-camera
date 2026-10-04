#!/usr/bin/env bash
#
# Build a small, low-res time-lapse ON THE PI, straight from the SD card.
#
# The point is to see what the footage looks like without first shifting
# gigabytes of JPEGs to the archive drive. You get back a ~10-30MB MP4 instead
# of several GB of stills. Not for editing - use make-timelapse.sh on the Mac
# for the real ProRes master.
#
# Usage (on the Pi):
#   ./preview.sh                    # today
#   ./preview.sh 2026-08-01         # one day
#   ./preview.sh 2026-08-01 2026-08-02
#   ./preview.sh 2026-08-01 2026-08-02 4    # every 4th frame, much faster
#
# Normally driven from the Mac by quicklook.sh, which runs this and fetches
# the result in one go.
#
set -euo pipefail

CAPTURES="$HOME/captures"
FPS=60
WIDTH=1280

START="${1:-$(date +%F)}"
END="${2:-$START}"
STEP="${3:-1}"          # take every Nth frame; 1 = all of them

OUT="/tmp/preview_${START}_to_${END}.mp4"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

n=0; kept=0
d="$START"
while :; do
  dir="$CAPTURES/$d"
  if [ -d "$dir" ]; then
    for f in "$dir"/*.jpg; do
      [ -e "$f" ] || continue
      n=$((n + 1))
      if [ $(( (n - 1) % STEP )) -eq 0 ]; then
        kept=$((kept + 1))
        ln -s "$f" "$(printf '%s/%06d.jpg' "$TMP" "$kept")"
      fi
    done
  fi
  [ "$d" = "$END" ] && break
  d="$(date -d "$d + 1 day" +%F)"   # GNU date (Linux)
done

if [ "$kept" -eq 0 ]; then
  echo "No frames found between $START and $END under $CAPTURES" >&2
  exit 1
fi

echo "Encoding $kept frames (of $n) at ${WIDTH}px wide..." >&2
ffmpeg -y -loglevel error -stats \
  -framerate "$FPS" -i "$TMP/%06d.jpg" \
  -vf "scale=${WIDTH}:-2" \
  -c:v libx264 -preset veryfast -crf 26 -pix_fmt yuv420p \
  -movflags +faststart "$OUT" >&2

echo "$OUT"
