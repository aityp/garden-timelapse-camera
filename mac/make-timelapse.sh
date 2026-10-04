#!/usr/bin/env bash
#
# Build ONE time-lapse clip from a date range of frames.
#
# Two very different jobs, hence the --format option:
#   prores (default)  edit master for Final Cut. Beautiful, retimes cleanly,
#                     and ENORMOUS: roughly 100MB per second of video, so a
#                     full year would be ~570GB. Only use it for clips you are
#                     actually going to cut with.
#   h265 / h264       deliverable for long-form uploads. A 90-minute slow-TV
#                     piece lands near 25-30GB instead of 570GB.
#
# Usage:
#   make-timelapse.sh [options] START END [OUTPUT]
#
#   -s, --step N       use every Nth frame (default 1). This is how you set
#                      pacing: at 60fps every frame gives 1 second of video per
#                      hour of real time, so --step 6 gives 10 seconds per day
#                      instead of 60.
#   -m, --per-minute   keep only the first frame of each minute, so fast-mode
#                      bursts play at the same pace as normal capture. --step
#                      then applies to what is left.
#   -f, --format FMT   prores | h265 | h264   (default prores)
#   -r, --res WxH      output resolution (default 3840x2160)
#       --fps N        output frame rate (default 60)
#
# Examples:
#   make-timelapse.sh 2026-08-01 2026-08-01
#   make-timelapse.sh --step 6 2026-08-01 2026-08-07
#   make-timelapse.sh --per-minute 2026-09-22 2026-09-30
#   make-timelapse.sh --format h265 --step 30 2026-01-01 2026-12-31
#
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
[ -f "$HERE/config.sh" ] || { echo "No config.sh next to this script - copy config.example.sh to config.sh and edit it." >&2; exit 1; }
source "$HERE/config.sh"

FPS=60
WIDTH=3840
HEIGHT=2160
STEP=1
PER_MINUTE=0
FORMAT=prores

while [ $# -gt 0 ]; do
  case "$1" in
    -s|--step)   STEP="$2"; shift 2 ;;
    -m|--per-minute) PER_MINUTE=1; shift ;;
    -f|--format) FORMAT="$2"; shift 2 ;;
    -r|--res)    WIDTH="${2%x*}"; HEIGHT="${2#*x}"; shift 2 ;;
    --fps)       FPS="$2"; shift 2 ;;
    -h|--help)   sed -n '2,30p' "$0"; exit 0 ;;
    -*)          echo "Unknown option: $1" >&2; exit 1 ;;
    *)           break ;;
  esac
done

START="${1:?start date YYYY-MM-DD}"
END="${2:?end date YYYY-MM-DD}"

case "$FORMAT" in
  prores) EXT=mov ;;
  h265|h264) EXT=mp4 ;;
  *) echo "Unknown format: $FORMAT (want prores, h265 or h264)" >&2; exit 1 ;;
esac

SUFFIX=""
[ "$PER_MINUTE" -eq 1 ] && SUFFIX="_per-minute"
[ "$STEP" -ne 1 ] && SUFFIX="${SUFFIX}_step${STEP}"
OUT="${3:-$OUTDIR/timelapse_${START}_to_${END}${SUFFIX}.${EXT}}"

# Validate the dates before looping over them - a bad or reversed range must
# fail loudly here, not spin forever incrementing past END.
for d_check in "$START" "$END"; do
  date -j -f %Y-%m-%d "$d_check" +%Y-%m-%d >/dev/null 2>&1 \
    || { echo "Invalid date: $d_check (want YYYY-MM-DD)" >&2; exit 1; }
done
if [[ "$START" > "$END" ]]; then
  echo "Start date $START is after end date $END" >&2
  exit 1
fi
[ "$STEP" -ge 1 ] 2>/dev/null || { echo "--step must be 1 or more" >&2; exit 1; }

if [ ! -d "$DRIVE" ]; then
  echo "$DRIVE is not mounted. Plug the archive drive in, or use quicklook.sh" >&2
  echo "on the Pi if you just want to see the footage without the drive." >&2
  exit 1
fi

mkdir -p "$OUTDIR"

# Sequentially-numbered symlinks let ffmpeg treat frames spread across dated
# folders as one ordered image sequence.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

seen=0; kept=0; last_minute=""
d="$START"
while :; do
  dir="$FRAMES/$d"
  if [ -d "$dir" ]; then
    for f in "$dir"/*.jpg; do
      [ -e "$f" ] || continue
      if [ "$PER_MINUTE" -eq 1 ]; then
        # garden_YYYY-MM-DD_HHMMSS.jpg -> YYYY-MM-DD_HHMM
        b="${f##*/}"; minute="${b:7:10}_${b:18:4}"
        [ "$minute" = "$last_minute" ] && continue
        last_minute="$minute"
      fi
      seen=$((seen + 1))
      if [ $(( (seen - 1) % STEP )) -eq 0 ]; then
        kept=$((kept + 1))
        ln -s "$f" "$(printf '%s/%06d.jpg' "$TMP" "$kept")"
      fi
    done
  fi
  [ "$d" = "$END" ] && break
  d="$(date -j -v+1d -f %Y-%m-%d "$d" +%Y-%m-%d)"   # BSD/macOS date increment
done

if [ "$kept" -eq 0 ]; then
  echo "No frames found between $START and $END under $FRAMES" >&2
  exit 1
fi

echo "Stitching $kept frames (of $seen available) -> $OUT"
echo "  ${WIDTH}x${HEIGHT} @ ${FPS}fps, $FORMAT, step $STEP$([ "$PER_MINUTE" -eq 1 ] && echo ', one frame per minute')"

# Colour handling: the JPEGs are full-range BT.601; output is expected to be
# limited-range BT.709. Convert explicitly in the scaler and tag the stream, or
# FCP will interpret the colours slightly off (greens especially).
SCALE="scale=${WIDTH}:${HEIGHT}:flags=lanczos:in_range=jpeg:in_color_matrix=bt601:out_range=limited:out_color_matrix=bt709"
TAGS=(-color_range tv -colorspace bt709 -color_primaries bt709 -color_trc bt709)

case "$FORMAT" in
  prores) CODEC=(-c:v prores_ks -profile:v 1 -vendor apl0 -pix_fmt yuv422p10le) ;;
  h265)   CODEC=(-c:v libx265 -crf 20 -preset medium -pix_fmt yuv420p -tag:v hvc1 -movflags +faststart) ;;
  h264)   CODEC=(-c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p -movflags +faststart) ;;
esac

ffmpeg -y -framerate "$FPS" -i "$TMP/%06d.jpg" -vf "$SCALE" \
  "${CODEC[@]}" "${TAGS[@]}" "$OUT"

echo "Done: $OUT"
echo "  ($kept frames = ~$((kept / FPS))s at ${FPS}fps, $(du -h "$OUT" | cut -f1))"
