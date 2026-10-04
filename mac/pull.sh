#!/usr/bin/env bash
#
# Pull new garden-camera frames from the Pi to the archive drive.
#
# Triggered by launchd (com.atypical.gardencam.pull.plist) the moment the drive
# mounts, plus hourly while it stays connected. launchd never runs two copies of
# the same job label at once, so overlapping runs can't happen. Safe to run any
# time: it is a plain incremental rsync, so a missed run just catches up.
#
# Requires key-based SSH from this Mac to the Pi (a background job can't type a
# password). Until keys are set up it will quietly no-op. See README.
#
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
[ -f "$HERE/config.sh" ] || { echo "No config.sh next to this script - copy config.example.sh to config.sh and edit it." >&2; exit 1; }
source "$HERE/config.sh"

DEST="$FRAMES"
LOG="$HOME/Library/Logs/gardencam-pull.log"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

# Keep the log from growing forever: trim to the last 2000 lines past ~1MB.
if [ -f "$LOG" ] && [ "$(stat -f%z "$LOG")" -gt 1048576 ]; then
  tail -n 2000 "$LOG" > "$LOG.trim" && mv "$LOG.trim" "$LOG"
fi

# 1. Only run if the archive drive is actually mounted.
if [ ! -d "$DRIVE" ]; then
  echo "$(ts) $DRIVE not mounted — skipping" >> "$LOG"
  exit 0
fi

mkdir -p "$DEST"

# 2. Bail quietly if the Pi isn't reachable (asleep, off the network, no key yet).
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "$PI" true 2>/dev/null; then
  echo "$(ts) Pi not reachable (or SSH key not set up) — skipping" >> "$LOG"
  exit 0
fi

# 3. Incremental pull. Notes:
#    - no --delete, on purpose: when the Pi prunes its card we must NOT delete
#      the copies here. This drive is the permanent home.
#    - no -z: JPEGs are already compressed; recompressing burns Pi CPU for
#      nothing on a gigabit LAN.
#    - --partial-dir keeps interrupted transfers out of the archive tree so a
#      half-copied frame can never be mistaken for a real one.
#    - exclude the capture script's in-progress .part files.
#    - FULL PATH to Homebrew rsync, not bare `rsync`, and NOT optional. macOS
#      blocks a launchd background job from writing to an external volume unless
#      the exact binary doing the write has Full Disk Access. The system
#      /usr/bin/rsync cannot hold that grant; a Homebrew rsync can. So we call the
#      Homebrew one by absolute path and grant THAT in Full Disk Access. Path is
#      Apple-silicon; on Intel it is /usr/local/opt/rsync/bin/rsync (brew --prefix
#      rsync). Runs fine from Terminal either way; this only matters under launchd.
echo "$(ts) pulling from $PI ..." >> "$LOG"
/opt/homebrew/opt/rsync/bin/rsync -rt --partial-dir=.rsync-partial --prune-empty-dirs \
  --exclude '.*.part' --exclude '.rsync-partial/' \
  -e "ssh -o ConnectTimeout=10" \
  "$PI:$PI_DIR" "$DEST/" >> "$LOG" 2>&1

# 4. Videos recorded with film-on. Unlike frames, these are MOVED off the Pi
#    (--remove-source-files): they are big, and nothing on the Pi prunes them.
#    Only finished .mp4s are taken (film-wrap writes .part then renames), and the
#    whole step is skipped unless the film service is fully stopped, so a
#    recording or wrap in progress is never touched.
VIDEOS="$BASE/videos"
film_state="$(ssh -o ConnectTimeout=10 "$PI" systemctl is-active garden-cam-film.service 2>/dev/null || true)"
if [ "$film_state" = "inactive" ] || [ "$film_state" = "failed" ] || [ "$film_state" = "unknown" ]; then
  mkdir -p "$VIDEOS"
  /opt/homebrew/opt/rsync/bin/rsync -rt --partial-dir=.rsync-partial --remove-source-files \
    --include '*.mp4' --exclude '*' \
    -e "ssh -o ConnectTimeout=10" \
    "$PI:videos/" "$VIDEOS/" >> "$LOG" 2>&1 || echo "$(ts) no videos to pull" >> "$LOG"
else
  echo "$(ts) filming in progress ($film_state) — leaving videos for next run" >> "$LOG"
fi
echo "$(ts) pull complete" >> "$LOG"
