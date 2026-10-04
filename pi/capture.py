#!/usr/bin/env python3
"""
Garden time-lapse camera — capture one daylight frame.

Run once per minute by garden-cam-capture.timer. Each run is independent, so
it survives reboots and PoE blips cleanly: check daylight, take one shot if it
is daytime, prune the card if it is getting full, exit.

- Full 12MP SDR still (4608x2592)
- Focus LOCKED (a distant garden never changes distance, so no hunting)
- White balance and exposure AUTO (daylight colour/brightness should drift
  through the day and the seasons — that drift is the point of the time-lapse)
- Daylight only, sunrise to sunset, computed from lat/long so it tracks the year
"""

import subprocess
import sys
import shutil
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from astral import LocationInfo
from astral.sun import sun

# ------------------------------- CONFIG -------------------------------
# Your location comes from config.py (copy config.example.py to config.py and
# edit it). Without one the example below is used (Greenwich, London), so the
# script still runs, but at the wrong sunrise/sunset times for anywhere else.
try:
    from config import LAT, LON, TZ
    CONFIGURED = True
except ImportError:
    LAT, LON, TZ = 51.4769, -0.0005, "Europe/London"
    CONFIGURED = False

CAPTURE_DIR = Path.home() / "captures"

LENS_POSITION = 0.0      # 0.0 = infinity focus (correct for a distant garden). Locked.
WIDTH = 4608             # full 12MP
HEIGHT = 2592
JPEG_QUALITY = 95
SETTLE_MS = 2000         # let auto-exposure / AWB settle before the shot
EV = 0.0                 # exposure compensation; try -0.3 if bright skies blow out

# How far below the horizon the sun must be before we stop/start shooting.
# Capturing well past sunset means the time-lapse fades naturally into darkness
# and back, so day-to-night reads properly in the edit with no transition work.
#   6  = civil twilight      (still fairly light, ~30 min past sunset)
#   12 = nautical twilight   (genuinely dusky, ~70 min past sunset)  <- default
#   18 = astronomical, fully dark. WARNING: does not occur at all at UK latitudes
#        between roughly late May and mid July, so it will fail in midsummer.
# 0 falls back to plain sunrise/sunset.
DEPRESSION = 12

# Prune oldest frames once the card passes this fraction full.
PRUNE_AT_USED = 0.85
# ----------------------------------------------------------------------


def shooting_window(now: datetime):
    """Start/end of today's capture window, widening past sunset by DEPRESSION.

    Falls back progressively: a depression angle the sun never reaches (which
    happens in midsummer this far north) raises, so step down rather than lose
    the whole day's capture.
    """
    obs = LocationInfo(latitude=LAT, longitude=LON).observer
    tz = ZoneInfo(TZ)
    for depression in (DEPRESSION, 12, 6, 0):
        try:
            if depression == 0:
                e = sun(obs, date=now.date(), tzinfo=tz)
                return e["sunrise"], e["sunset"]
            e = sun(obs, date=now.date(), tzinfo=tz,
                    dawn_dusk_depression=depression)
            return e["dawn"], e["dusk"]
        except (ValueError, TypeError):
            continue  # sun never reaches that angle today, or old astral API
    raise RuntimeError("could not compute a shooting window")


def is_daylight(now: datetime) -> bool:
    start, end = shooting_window(now)
    return start <= now <= end


def capture(now: datetime) -> None:
    day_dir = CAPTURE_DIR / now.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    out = day_dir / f"garden_{now.strftime('%Y-%m-%d_%H%M%S')}.jpg"
    # Write to a hidden .part file, then atomically rename. The Mac's rsync
    # (and the pruner) can therefore never see a half-written frame.
    tmp = day_dir / f".{out.name}.part"
    cmd = [
        "rpicam-still",
        "-o", str(tmp),
        "--encoding", "jpg",                  # explicit: .part hides the extension
        "--width", str(WIDTH),
        "--height", str(HEIGHT),
        "-q", str(JPEG_QUALITY),
        "-t", str(SETTLE_MS),
        "-n",                                 # no preview (headless)
        "--autofocus-mode", "manual",         # lock focus...
        "--lens-position", str(LENS_POSITION),  # ...at infinity
        "--awb", "auto",                      # colour tracks the daylight
        "--ev", str(EV),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        tmp.unlink(missing_ok=True)
        # Surface rpicam's actual complaint in the journal, not just "exit 1".
        raise RuntimeError(
            f"rpicam-still exited {result.returncode}: {result.stderr.strip()[-500:]}"
        )
    tmp.replace(out)
    print(f"captured {out}")


def prune() -> None:
    # Sweep orphaned .part files first (a capture killed mid-write leaves one).
    # Anything older than 10 minutes is dead, not in-progress.
    cutoff = time.time() - 600
    for p in CAPTURE_DIR.glob("*/.*.part"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
                print(f"swept stale partial {p}")
        except OSError:
            pass

    total, used, free = shutil.disk_usage(CAPTURE_DIR)
    if used / total < PRUNE_AT_USED:
        return
    # Oldest first (folder names sort chronologically, so do the file paths).
    for f in sorted(CAPTURE_DIR.glob("*/*.jpg")):
        total, used, free = shutil.disk_usage(CAPTURE_DIR)
        if used / total < PRUNE_AT_USED:
            break
        try:
            f.unlink()
            print(f"pruned {f}")
        except OSError:
            pass
    # Tidy up any now-empty day folders.
    for d in sorted(CAPTURE_DIR.glob("*")):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()


def main() -> None:
    now = datetime.now(ZoneInfo(TZ))
    if not is_daylight(now):
        return  # night — nothing to do
    if not CONFIGURED:
        print("note: no config.py, using the example location - "
              "copy config.example.py to config.py and set yours")
    try:
        capture(now)
    except RuntimeError as e:
        print(f"capture failed: {e}", file=sys.stderr)
        sys.exit(1)
    prune()


if __name__ == "__main__":
    main()
