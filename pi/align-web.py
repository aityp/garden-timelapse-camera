#!/usr/bin/env python3
"""
Re-alignment view for the garden camera — line the live view back up with a
known-good past frame.

Same live MJPEG stream as aim-web.py, but with your last well-aligned frame laid
over the top as an adjustable ghost, so you can put the camera back exactly where
it was even when the scene itself has changed (a fence taken down, a bed dug over,
snow, whatever). Open on any device at the top of the ladder:

    http://garden-cam.local:8080

The stream and the reference share the SAME field of view (both forced to
--mode 2304:1296, the full-sensor 16:9 that capture.py stills), so overlaying an
old frame on the live one is a true 1:1 comparison, not an approximation.

How to use it:
    1. Pick a frame from when you were happy with the framing. Either point this
       tool straight at one already on the Pi:

           ./align-web.py --ref ~/captures/2026-08-15/garden_2026-08-15_120000.jpg

       or start it with no --ref and load the frame from the phone with the
       "reference" file button on the page (AirDrop it to the phone first).
    2. On the page: drag OPACITY to about 50% so you see both at once. Adjust the
       camera until the live scene slides under the ghost and the fixed things
       (rooflines, posts, the shed base, a drainpipe) sit exactly on top of their
       ghost. Ignore anything that has actually changed on the ground.
    3. Hit BLINK for the final tweak — it flashes between live and reference, so
       any remaining misalignment visibly jumps. Stop when nothing jumps.
    4. Lock the mount. Done.

The camera is single-access, so stop the capture timer first if it is daytime
(at night capture.py never opens the camera, so there is no conflict):
    sudo systemctl stop garden-cam-capture.timer
    ./align-web.py --ref <frame>
    (Ctrl-C when done)
    sudo systemctl start garden-cam-capture.timer

ROTATION: rpicam supports 180 only, never 90. If the live view is upside down set
ROTATION = 180 below (and it will already be right in capture.py if you set it
there too). A sideways view is a physical mounting problem, not a flag.
"""

import argparse
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
<title>Garden Cam - Alignment</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  html,body{margin:0;background:#111;color:#eee;font:14px system-ui,sans-serif}
  .wrap{position:relative;width:100vw;max-width:100%;background:#000}
  /* Live and reference occupy the exact same box; both are 16:9 so they register
     1:1. object-fit:fill pins the reference to the box even if it is a full-res
     still, so it can never drift a few pixels from the live frame. */
  .layer{display:block;width:100%;height:auto}
  #ref{position:absolute;inset:0;width:100%;height:100%;object-fit:fill;
       pointer-events:none;opacity:.5}
  .grid{position:absolute;inset:0;pointer-events:none}
  .grid div{position:absolute;background:rgba(255,255,255,.45)}
  .grid .v{top:0;bottom:0;width:1px}
  .grid .h{left:0;right:0;height:1px}
  .bar{padding:8px 10px;background:#000;display:flex;gap:14px;align-items:center;
       flex-wrap:wrap}
  label{display:flex;gap:5px;align-items:center;user-select:none}
  input[type=range]{width:130px}
  button{background:#333;color:#eee;border:1px solid #555;border-radius:5px;
         padding:5px 10px;font:inherit}
  button.on{background:#c50;border-color:#e70}
  .hint{opacity:.6}
</style>
<div class="bar">
  <strong>Garden Cam</strong>
  <label>opacity <input type="range" id="op" min="0" max="100" value="50"></label>
  <button id="blink">blink</button>
  <label><input type="checkbox" id="g" checked> grid</label>
  <label class="hint">reference <input type="file" id="file" accept="image/*"></label>
  <span id="s" class="hint"></span>
</div>
<div class="wrap">
  <img class="layer" src="/stream" alt="live view" id="live">
  <img id="ref" alt="">
  <div class="grid" id="grid">
    <div class="v" style="left:33.33%"></div>
    <div class="v" style="left:66.66%"></div>
    <div class="h" style="top:33.33%"></div>
    <div class="h" style="top:66.66%"></div>
  </div>
</div>
<script>
  const ref=document.getElementById('ref'),
        op=document.getElementById('op'),
        blink=document.getElementById('blink'),
        g=document.getElementById('g'),
        grid=document.getElementById('grid'),
        file=document.getElementById('file'),
        s=document.getElementById('s'),
        live=document.getElementById('live');

  // A reference passed with --ref is served at /reference. Try it; if there is
  // none, the file button is the way in.
  ref.onerror=()=>{ if(!ref.dataset.user){ ref.removeAttribute('src');
    s.textContent='no reference loaded - use the file button'; } };
  ref.onload=()=>{ s.textContent=''; };
  ref.src='/reference?'+Date.now();

  op.oninput=()=>{ if(!blinking) ref.style.opacity=op.value/100; };
  g.onchange=()=>grid.style.display=g.checked?'block':'none';

  // Load a reference straight off the phone (no Pi copy needed).
  file.onchange=()=>{ const f=file.files[0]; if(!f) return;
    ref.dataset.user='1'; ref.src=URL.createObjectURL(f); };

  // Blink comparator: flip the ghost fully on/off so misalignment jumps.
  let blinking=false, timer=null;
  blink.onclick=()=>{
    blinking=!blinking; blink.classList.toggle('on',blinking);
    if(blinking){ let on=true;
      timer=setInterval(()=>{ ref.style.opacity=on?1:0; on=!on; },450); }
    else{ clearInterval(timer); ref.style.opacity=op.value/100; }
  };

  // Nudge the live stream back if the phone sleeps and the connection drops.
  live.onerror=()=>setTimeout(()=>live.src='/stream?'+Date.now(),1000);
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
reference = None        # bytes of the --ref frame, or None (use the file button)


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
        elif self.path.startswith("/reference"):
            if reference is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(reference)))
            self.send_header("Cache-Control", "no-cache, private")
            self.end_headers()
            self.wfile.write(reference)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Garden camera re-alignment view.")
    ap.add_argument("--ref", metavar="FRAME.jpg",
                    help="a known-good past frame to ghost over the live view "
                         "(optional; you can also load one from the phone in the "
                         "page).")
    args = ap.parse_args()

    if args.ref:
        try:
            with open(args.ref, "rb") as f:
                reference = f.read()
            print(f"Reference loaded: {args.ref} ({len(reference) // 1024} KB)")
        except OSError as e:
            raise SystemExit(f"could not read --ref {args.ref}: {e}")

    camera.start()
    print(f"Alignment view: http://{socket.gethostname()}.local:{PORT}   (Ctrl-C to stop)")
    if reference is None:
        print("No --ref given: load your reference frame from the file button on the page.")
    try:
        ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
