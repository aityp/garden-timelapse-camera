#!/usr/bin/env bash
#
# Live view for aiming the camera during install.
# Streams H.264 over TCP so you can watch on your Mac while you set the RAM mount.
#
# rpicam-vid --listen serves ONE client and exits when that client disconnects,
# so this loops: every time the viewer drops, it goes straight back to listening.
# That means you can close and reopen the viewer as often as you like while
# adjusting the mount, without SSHing back in. Ctrl-C to stop for good.
#
# NOTE: do not "test" the port with nc/telnet — connecting and immediately
# disconnecting is exactly what ends a stream (SIGPIPE). Just point the viewer
# at it; the viewer connecting IS the test.
#
# The camera is single-access. At night the capture timer never opens the camera
# (capture.py returns at the daylight check), so there is no conflict. In daylight,
# stop it first and start it again after:
#   sudo systemctl stop garden-cam-capture.timer
#   ./aim.sh
#   (Ctrl-C when done)
#   sudo systemctl start garden-cam-capture.timer
#
# On your Mac. The stream is raw H.264 with no container, so the player must be
# told the format explicitly with -f h264 or it will silently fail to open:
#   ffplay -f h264 -fflags nobuffer -flags low_delay -framedrop tcp://garden-cam.local:8888
#
# Focus is locked at infinity here to match the capture script.

PORT=8888

echo "Aim stream on port $PORT. Ctrl-C to stop."
echo "View on the Mac:  ffplay -f h264 -fflags nobuffer -flags low_delay -framedrop tcp://garden-cam.local:$PORT"
echo

# Ctrl-C should kill the whole loop, not just the current rpicam-vid.
trap 'echo; echo "Stopped."; exit 0' INT TERM

while :; do
  echo "$(date '+%H:%M:%S') waiting for viewer..."
  # SIGPIPE on client disconnect is expected and fine; just loop round again.
  # --mode 2304:1296 is REQUIRED: without it, asking for 720p makes the sensor
  # select its 1536x864 mode, which is a hardware crop ((768,432)/3072x1728) and
  # previews a narrower view than capture.py actually stills. 2304x1296 is
  # full-sensor, so preview framing matches the real captures.
  rpicam-vid \
    -t 0 \
    -n \
    --mode 2304:1296 \
    --width 1280 --height 720 --framerate 15 \
    --autofocus-mode manual --lens-position 0.0 \
    --inline --listen \
    -o "tcp://0.0.0.0:$PORT" 2>/dev/null
  echo "$(date '+%H:%M:%S') viewer disconnected"
  sleep 1
done
