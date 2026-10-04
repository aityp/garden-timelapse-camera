# Settings for the Mac-side garden-cam scripts (sourced, not run).
#
# COPY THIS FILE to config.sh (same folder) and edit your copy:
#     cp config.example.sh config.sh
# config.sh is yours alone: git ignores it, so updating the project never
# overwrites it.

PI="gc@garden-cam.local"                 # user@hostname you chose for the Pi
PI_DIR="captures/"                       # relative to that user's home on the Pi

DRIVE="/Volumes/Archive"                 # where frames are kept (your drive or a folder)
BASE="$DRIVE/garden-timelapse"
FRAMES="$BASE/frames"
OUTDIR="$BASE/timelapses"
