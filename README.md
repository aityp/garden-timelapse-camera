# Garden Time-Lapse Camera

The software for a Raspberry Pi garden time-lapse camera. The Pi
takes a full 12MP photograph every minute in daylight and looks after its own
storage, your Mac collects the frames automatically, and one command turns any
date range into a video. Free and open source: use it, fork it, improve it.

**Watch it in action:** [the build video on YouTube](https://youtu.be/OxDAe00Okmk).

A step-by-step build guide is being written and will be added to this repository.
Until then, this README should be enough to get everything running if you are
comfortable following commands in a terminal.

**How it was made.** This code was written with AI (Claude) and is tested on a
real camera in my garden.

## What it does

- **Capture (Pi).** One full 12MP still a minute, daylight only. The window is
  worked out from your latitude and longitude, so it follows the seasons, and it
  runs a little past sunset so the video fades into darkness. Focus is locked at
  infinity, and white balance and exposure are automatic. Frames go into dated
  folders, and when the SD card passes 85% full the oldest are deleted first.
- **Pull (Mac).** The Mac copies new frames to your archive drive the moment the
  drive is plugged in, and hourly while it stays connected. It never deletes
  anything from the archive, even after the Pi prunes its own card.
- **Make a time-lapse (Mac).** Any date range becomes one 4K, 60fps clip.
- **Extras.** Aiming tools for the install, a fast mode for bursts of frames, a
  film mode for recording video, and a quick preview that does not need the
  archive drive.

## What you need

| | |
|---|---|
| Raspberry Pi 4 Model B, 2GB | the camera's brain; 2GB is plenty |
| Camera Module 3 **Wide** (Sony IMX708, 12MP, 120° view) | the wide lens is what takes in a whole garden from close to a wall |
| Waveshare **PoE HAT (E)** | takes power off the Ethernet cable (802.3af, low-profile) |
| TP-Link **TL-POE160S** PoE injector | puts the power onto the cable, at the router end |
| SanDisk **High Endurance** 64GB microSD card | built for continuous writing, which a camera is |
| **RAM Mounts** short double socket arm, 1" ball (RAM-B-201U-A) and two **FANAUE** 1" ball diamond bases | a ball-and-socket mount: one base on the timber, one on the box, joined by the arm, so you can aim it and lock it |
| [British General IP66 weatherproof junction box, 60mm x 120mm x 120mm](https://www.screwfix.com/p/british-general-ip66-57a-5-terminal-weatherproof-outdoor-junction-box-60mm-x-120mm-x-120mm/33518) | the enclosure for the Pi and camera |
| 3D-printed Pi mount: [Raspberry Pi Open Wall Mount by mintonette](https://www.thingiverse.com/thing:5183183) | holds the Pi inside the box |
| 3D-printed camera bracket: [Raspberry Pi Camera Module 3 Wide bracket](https://www.printables.com/model/1865748-raspberry-pi-camera-module-3-wide-bracket) (M2 and M3 versions) | holds the camera board against the window in the box |
| IP68 cable gland | seals the Ethernet cable's entry into the box |
| A Mac | the scripts that pull and assemble use macOS tools (launchd, `stat -f`) |

```
Router -- patch lead -- PoE injector (mains, indoors)
       -- Ethernet cable run to the camera --
       -- PoE HAT on the Pi (outdoors) -- Pi + camera
```

The injector puts power onto the Ethernet line and the HAT takes it off again.

Set the Pi up with Raspberry Pi OS Lite and the Raspberry Pi Imager, choosing
**hostname `garden-cam`**, **username `gc`** and enabling SSH. Those two names
are written into the service files and scripts. If you choose different ones,
see [Using different names](#using-different-names).

## Get the code

Download this repository to your Mac and open Terminal in the folder it makes.
Every command in the next section is run from there.

```bash
git clone https://github.com/aityp/garden-timelapse-camera.git
cd garden-timelapse-camera
```

(Without `git`, the green **Code** button on this page also gives you a zip to
download and unpack.)

## Your settings

Two small files hold the details that are yours. Make them now, so they are ready
when you copy things across in the next two sections. Both are made by copying an
example file that is already in the repository, and git ignores your copies, so
pulling an update never overwrites them.

```
pi/    runs on the Raspberry Pi
mac/   runs on your Mac
```

On your Mac, in this repository's folder:

```bash
cp pi/config.example.py pi/config.py
cp mac/config.example.sh mac/config.sh
```

Then edit each copy. Any plain text editor will do. In Terminal, `nano pi/config.py`
opens one (save with Ctrl-O then Enter, quit with Ctrl-X), or `open -e pi/config.py`
opens it in TextEdit.

**`pi/config.py`** is where your camera is. It has three lines and you change the
values:

```python
LAT = 51.4769            # degrees north (south is negative)
LON = -0.0005            # degrees east (west is negative)
TZ = "Europe/London"     # your timezone name, e.g. "America/New_York"
```

Any map app will give you your latitude and longitude (in Apple Maps or Google
Maps, press and hold on your garden). The timezone name is the one in the "TZ
identifier" column of
[Wikipedia's list of time zones](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones).
The Pi works out from these when the sun rises and sets and only takes photographs
in daylight. The example values are Greenwich, London, so if you skip this anywhere
else the photographs are taken at the wrong hours.

**`mac/config.sh`** is where things go on your Mac. The two lines you may need to
change are:

```bash
PI="gc@garden-cam.local"      # the Pi's login: username@hostname.local
DRIVE="/Volumes/Archive"      # where the frames are kept
```

Leave `PI` alone if you used `gc` and `garden-cam` in the Imager, and otherwise put
the username and hostname you chose. `DRIVE` is the drive or folder you want the
frames kept in. It must already exist, and `ls /Volumes` lists the names of your
connected drives. The frames are copied into `garden-timelapse/frames` inside it,
and finished time-lapses are written to `garden-timelapse/timelapses`.

---

## Set up the Pi

On your Mac, from this repository, copy the Pi files across. This includes the
`config.py` you just made:

```bash
ssh gc@garden-cam.local mkdir -p garden-cam
scp pi/* gc@garden-cam.local:garden-cam/
```

Then on the Pi:

```bash
sudo apt update && sudo apt install -y python3-astral ffmpeg
cd ~/garden-cam
chmod +x aim.sh aim-web.py align-web.py preview.sh fast-on fast-off fast-status film-on film-off film-status film-wrap
```

Check the Pi can see the camera:

```bash
rpicam-hello --list-cameras
```

It should list one camera, an `imx708_wide` for the Camera Module 3 Wide. If it
says no cameras are available, shut the Pi down, unplug it, and reseat the ribbon
cable at both ends.

Try one capture by hand. By day this takes a photograph, and at night it prints
nothing, because it only shoots in daylight:

```bash
python3 capture.py
ls ~/captures
```

Then install everything with one command. It copies all the service and timer files
into place, and turns on the capture timer, which runs `capture.py` every minute
from now on (including after a power cut), and the nightly fast-mode reset:

```bash
sudo cp *.service *.timer /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now garden-cam-capture.timer garden-cam-fast-reset.timer
```

Check that it is running, and watch captures happen:

```bash
systemctl status garden-cam-capture.timer
journalctl -u garden-cam-capture.service -f
```

Two things worth knowing. The Pi runs its own copy of every script, so after you
change anything in `pi/`, copy it across again before testing. And a capture that
has not finished in 15 seconds is killed by the service (`TimeoutStartSec`), so
one wedged camera cannot block every capture after it.

## Set up the Mac

Install the tools the scripts use:

```bash
brew install rsync ffmpeg
```

Make a folder and copy the scripts into it. This includes the `config.sh` you just
made:

```bash
mkdir -p ~/garden-cam
cp mac/pull.sh mac/quicklook.sh mac/make-timelapse.sh mac/config.sh ~/garden-cam/
cd ~/garden-cam
chmod +x pull.sh quicklook.sh make-timelapse.sh
```

`pull.sh` needs to log in to the Pi without a password, because a background job
cannot type one:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/gardencam -N ""
ssh-copy-id -i ~/.ssh/gardencam.pub gc@garden-cam.local
```

Add this to `~/.ssh/config`:

```
Host garden-cam.local
  User gc
  IdentityFile ~/.ssh/gardencam
```

and check it logs in with no password prompt:

```bash
ssh gc@garden-cam.local true && echo "key OK"
```

Run the first pull by hand:

```bash
~/garden-cam/pull.sh
tail ~/Library/Logs/gardencam-pull.log
```

To have it run by itself whenever the drive is plugged in, and hourly while it
stays connected, install the launchd job. First open `mac/com.atypical.gardencam.pull.plist`
and replace `YOU` with your Mac username (`whoami` shows it), then, from this repository:

```bash
cp mac/com.atypical.gardencam.pull.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.atypical.gardencam.pull.plist
```

`pull.sh` calls Homebrew's rsync by its full path (`/opt/homebrew/opt/rsync/bin/rsync`,
or `/usr/local/opt/rsync/bin/rsync` on an Intel Mac, which `brew --prefix rsync`
will confirm). macOS only lets a background job write to an external drive if the
exact program doing the writing has Full Disk Access, and Apple's built-in rsync
cannot be given it. Add the Homebrew one under System Settings, Privacy &
Security, Full Disk Access. This only matters for the launchd job. Running
`~/garden-cam/pull.sh` yourself in Terminal works without it.

---

## Aiming the camera

The camera is single-access, so in daylight stop the capture timer first, and start
it again afterwards. At night `capture.py` never opens the camera, so there is no
conflict.

```bash
sudo systemctl stop garden-cam-capture.timer
# ...aim the camera, then Ctrl-C...
sudo systemctl start garden-cam-capture.timer
```

There are three ways to see what the camera sees.

**In a phone or browser (best up a ladder).** Run `./aim-web.py` on the Pi and open
`http://garden-cam.local:8080`. It shows a live view with a rule-of-thirds grid to
help you level the horizon, and several people can watch at once.

**With a ghost of an earlier photograph.** `./align-web.py --ref <a past frame>`
serves the same view with a photograph from when you were happy with the framing
laid over it. It is for putting the camera back exactly where it was after you
knock it, or after the scene itself has changed.

```bash
./align-web.py --ref ~/captures/2026-08-15/garden_2026-08-15_120000.jpg
```

An opacity slider lets you see both at once, the blink button flashes between live
and reference so any drift visibly jumps, and the file button loads a reference
straight from your phone if you start it without `--ref`. Line up things that
cannot move (rooflines, posts, a drainpipe) and ignore anything that has changed.

**On your Mac.** Run `./aim.sh` on the Pi, then:

```bash
ffplay -f h264 -fflags nobuffer -flags low_delay -framedrop tcp://garden-cam.local:8888
```

The `-f h264` is required, and the stream ends if you probe the port with `nc` or
telnet, so just point the player at it.

**The field of view is deliberate.** All the aiming tools and the film service pass
`--mode 2304:1296`. Without it, asking for 720p makes the sensor pick a mode that
is a hardware crop, so the preview shows a narrower view than the photographs
actually capture. Do not remove it.

**Rotation.** The camera supports 180 degrees only, never 90. If the view is upside
down, set `ROTATION = 180` in the aiming tools and add `"--rotation", "180"` to the
`rpicam-still` command in `capture.py` (and `--rotation 180` to the film service).
If it is sideways the camera has to be turned physically, because the sensor is
natively landscape.

## Fast mode

Fast mode takes a frame every five seconds instead of every minute, for when you
want detail on a particular job. It is a toggle.

```bash
~/garden-cam/fast-on        # burst mode
~/garden-cam/fast-off       # back to one a minute
~/garden-cam/fast-status
```

It cannot get stuck on. The fast timer has no `[Install]` section, so it can never
be enabled and a reboot always returns to normal, and a nightly timer at 01:00
resets it as well. `capture.py` is not involved at all, because only how often it
is asked changes.

Fast-mode frames play much slower than the rest of a range when you make a
time-lapse. `make-timelapse.sh --per-minute` fixes that, as shown below.

## Film mode

Film mode stops both capture timers, records 1080p30 video into `~/videos/` on the
Pi using the same field of view and focus as the photographs, and puts everything
back when you stop. A forgotten recording stops itself after 30 minutes.

```bash
~/garden-cam/film-on
~/garden-cam/film-off       # stops, resumes normal capture, saves the video as .mp4
~/garden-cam/film-status    # filming / fast / normal, and whether frames are really being taken
```

`pull.sh` moves finished videos off the Pi to `videos/` next to your frames (unlike
frames they are removed from the Pi once copied, since nothing prunes them).

## Controlling it from your phone

The Shortcuts app on an iPhone can run a command on the Pi over SSH (the **Run
Script Over SSH** action), so a button on your home screen can start fast mode or
film mode, for example by running `~/garden-cam/film-on`. Those commands use
`sudo`, and a shortcut cannot type a password, so first allow them without one.
**On the Pi**, open the sudoers file for editing:

```bash
sudo visudo -f /etc/sudoers.d/garden-cam
```

and put this one line in it (use your Pi username in place of `gc`):

```
gc ALL=(root) NOPASSWD: /usr/bin/systemctl start garden-cam-capture.timer, /usr/bin/systemctl stop garden-cam-capture.timer, /usr/bin/systemctl start garden-cam-capture-fast.timer, /usr/bin/systemctl stop garden-cam-capture-fast.timer, /usr/bin/systemctl start garden-cam-film.service, /usr/bin/systemctl stop garden-cam-film.service
```

It allows exactly those commands and nothing else. `fast-status` and `film-status`
only read, so they need no rule.

---

## Making a time-lapse

```bash
~/garden-cam/make-timelapse.sh 2026-07-01 2026-09-30
```

writes a 4K, 60fps ProRes clip into `timelapses/` beside your frames. ProRes is an
editing format and is huge (about 100MB per second of video), so for something to
upload use `--format h265`. Other options:

```bash
make-timelapse.sh --step 6 2026-08-01 2026-08-07        # every 6th frame: faster pacing
make-timelapse.sh --per-minute 2026-09-22 2026-09-30    # keep fast-mode bursts at normal pace
make-timelapse.sh --format h265 --step 30 2026-01-01 2026-12-31
make-timelapse.sh --help
```

The clip is SDR (sRGB), so if your editing project is HDR, let your editor
colour-manage it in.

## Quick look, without the archive drive

`quicklook.sh` builds a small preview on the Pi straight off the SD card, copies
back just that MP4 and opens it. Nothing is pulled and the drive does not need to
be plugged in. It needs `preview.sh` and `ffmpeg` on the Pi.

```bash
~/garden-cam/quicklook.sh                       # today
~/garden-cam/quicklook.sh 2026-08-01 2026-08-02
~/garden-cam/quicklook.sh 2026-08-01 2026-08-02 4    # every 4th frame, faster
```

## Tuning

- **Interval.** `OnCalendar=*:0/1` in `garden-cam-capture.timer` is every minute.
  `*:0/2` is every two minutes.
- **Focus.** `LENS_POSITION = 0.0` in `capture.py` is infinity. If the near
  foreground matters, nudge it up a little (it is in dioptres, and 0.1 is about 10m).
- **Blown skies.** Set `EV = -0.3` or lower to protect the highlights.
- **Twilight.** `DEPRESSION` in `capture.py` sets how far past sunset it keeps
  shooting. 12 is nautical twilight, 6 is civil twilight, and 0 is plain
  sunrise to sunset.

## Using different names

The service files and scripts assume user `gc` and the folder `~/garden-cam` on the
Pi. If you chose something else, change it in these places:

- `garden-cam-capture.service`: `User=` and the path in `ExecStart=`
- `garden-cam-film.service` and `film-wrap`: the `/home/gc/` paths
- `mac/config.sh`: `PI=` and `PI_DIR=`
- the sudoers rule above

## If something is wrong

- **No photographs by day.** Run `journalctl -u garden-cam-capture.service -n 50`.
  `film-status` also says whether it is dark, capturing, or has gone quiet.
- **Photographs at the wrong hours.** Check `config.py` is in `~/garden-cam` on
  the Pi and holds your coordinates. The journal says "no config.py" if it is
  falling back to the example.
- **The pull does nothing.** Read `~/Library/Logs/gardencam-pull.log`. It skips
  quietly when the drive is not mounted, or when the Pi cannot be reached without a
  password.
- **A script on the Mac says "No config.sh".** Copy `config.example.sh` to
  `config.sh` next to the script and edit it.

## Licence

MIT. Use it however you like, and keep the copyright notice in `LICENSE` with it.
