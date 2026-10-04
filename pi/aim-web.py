#!/usr/bin/env python3
"""
Browser-based aiming view for the garden camera.

Serves an MJPEG stream over plain HTTP so you can frame the shot from a phone at
the top of the ladder instead of running back to a laptop. Open on any device:

    http://garden-cam.local:8080

Works in Safari/Chrome with no app to install. Supports several viewers at once
(one camera process, frames fanned out), so the phone and the laptop can both
watch while you adjust the RAM mount.

Includes a rule-of-thirds grid to help level the horizon and place the garden.

The camera is single-access. At night the capture timer never opens the camera
(capture.py exits at the daylight check) so there is no conflict. In daylight:
    sudo systemctl stop garden-cam-capture.timer
    ./aim-web.py
    (Ctrl-C when done)
    sudo systemctl start garden-cam-capture.timer

ROTATION: rpicam supports 180 only, never 90. If the image is upside down set
ROTATION = 180 below AND add "--rotation 180" to capture.py so stills match.
If the view is sideways the camera must be physically rotated: the sensor is
natively landscape and no flag will turn a portrait mounting into a wide shot.
"""

import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8080
WIDTH = 1280
HEIGHT = 720
FRAMERATE = 15
ROTATION = 0        # 0 or 180 only
LENS_POSITION = 0.0  # infinity, matches capture.py

JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"

PAGE = b"""<!doctype html>
<title>Garden Cam - Aiming</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  html,body{margin:0;background:#111;color:#eee;font:14px system-ui,sans-serif}
  .wrap{position:relative;width:100vw;max-width:100%}
  img{display:block;width:100%;height:auto}
  .grid{position:absolute;inset:0;pointer-events:none}
  .grid div{position:absolute;background:rgba(255,255,255,.45)}
  .grid .v{top:0;bottom:0;width:1px}
  .grid .h{left:0;right:0;height:1px}
  .bar{padding:8px 10px;background:#000;display:flex;gap:14px;align-items:center}
  label{display:flex;gap:5px;align-items:center;user-select:none}
</style>
<div class="bar">
  <strong>Garden Cam</strong>
  <label><input type="checkbox" id="g" checked> grid</label>
  <span id="s"></span>
</div>
<div class="wrap">
  <img src="/stream" alt="live view">
  <div class="grid" id="grid">
    <div class="v" style="left:33.33%"></div>
    <div class="v" style="left:66.66%"></div>
    <div class="h" style="top:33.33%"></div>
    <div class="h" style="top:66.66%"></div>
  </div>
</div>
<script>
  const g=document.getElementById('g'),grid=document.getElementById('grid');
  g.onchange=()=>grid.style.display=g.checked?'block':'none';
  // Nudge the stream back to life if the phone sleeps and the connection drops.
  const img=document.querySelector('img');
  img.onerror=()=>setTimeout(()=>img.src='/stream?'+Date.now(),1000);
</script>
"""


class Camera:
    """One rpicam-vid process; latest JPEG frame shared with all viewers."""

    def __init__(self):
        self.frame = None
        self.cond = threading.Condition()
        self.proc = None

    def start(self):
        cmd = [
            "rpicam-vid", "-t", "0", "-n",
            "--codec", "mjpeg",
            # CRITICAL: without an explicit --mode, asking for 720p makes the
            # sensor pick its 1536x864 mode, which is a hardware CROP
            # ((768,432)/3072x1728) and shows a NARROWER view than capture.py
            # actually stills. 2304x1296 is full-sensor (0,0)/4608x2592, so the
            # preview framing then matches the real captures. Never remove this.
            "--mode", "2304:1296",
            "--width", str(WIDTH), "--height", str(HEIGHT),
            "--framerate", str(FRAMERATE),
            "--autofocus-mode", "manual", "--lens-position", str(LENS_POSITION),
            "-o", "-",
        ]
        if ROTATION:
            cmd += ["--rotation", str(ROTATION)]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, bufsize=0)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        buf = b""
        while True:
            chunk = self.proc.stdout.read(4096)
            if not chunk:
                break
            buf += chunk
            # Pull out every complete JPEG sitting in the buffer.
            while True:
                start = buf.find(JPEG_SOI)
                end = buf.find(JPEG_EOI, start + 2)
                if start < 0 or end < 0:
                    break
                with self.cond:
                    self.frame = buf[start:end + 2]
                    self.cond.notify_all()
                buf = buf[end + 2:]

    def latest(self, previous):
        with self.cond:
            while self.frame is previous:
                self.cond.wait()
            return self.frame


camera = Camera()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *a):
        pass  # keep the console clean for the ladder

    def do_GET(self):
        if self.path.startswith("/stream"):
            self.send_response(200)
            self.send_header("Age", "0")
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Content-Type",
                             "multipart/x-mixed-replace; boundary=FRAME")
            self.end_headers()
            last = None
            try:
                while True:
                    last = camera.latest(last)
                    self.wfile.write(b"--FRAME\r\n")
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(last)))
                    self.end_headers()
                    self.wfile.write(last)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass  # viewer went away; other viewers carry on
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)


if __name__ == "__main__":
    camera.start()
    print(f"Aiming view: http://{socket.gethostname()}.local:{PORT}   (Ctrl-C to stop)")
    try:
        ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
