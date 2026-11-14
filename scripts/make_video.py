"""Record the guided demo as a captioned video for the pitch (docs/pitch/demo.mp4, plan A03 4.4)
and take the README's two screenshots (docs/demo_create_offer.png, docs/demo_weekly_results.png).

    python scripts/make_video.py                  # after `python tasks.py export`
    python scripts/make_video.py --seconds 11     # reading time per step (default 12)
    python scripts/make_video.py --no-video       # the screenshots only

Serves the exported site (site/) on a free local port, lets Playwright's Chromium walk through the
guided demo with generic restaurant names (decision D5: the deck and the video do not show real
brand names), and converts the recording to H.264 MP4 with the ffmpeg binary that imageio-ffmpeg
ships (uv group `media`). The tour's own captions explain every step, so no voice is needed. The
recording shows simulated customers, orders and profits, and says so on screen.
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
OUT = ROOT / "docs" / "pitch" / "demo.mp4"
UI = ROOT / "tests" / "ui"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for(url: str, seconds: float = 30) -> None:
    end = time.time() + seconds
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError(f"the static site did not answer at {url}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seconds", type=float, default=12.0, help="reading time per guided-demo step")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--no-video", action="store_true", help="only the README screenshots")
    a = ap.parse_args()
    if not (SITE / "index.html").exists():
        print("No site/ found: run `python tasks.py export` first.")
        return 1
    import imageio_ffmpeg

    port = free_port()
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(SITE)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for(f"http://127.0.0.1:{port}/data/config.json")
        url = f"http://127.0.0.1:{port}/#names=generic"
        shots = [str(ROOT / "docs" / "demo_create_offer.png"), str(ROOT / "docs" / "demo_weekly_results.png")]
        subprocess.run(["node", str(UI / "screenshots.js"), url, *shots], cwd=UI, check=True)
        print("wrote docs/demo_create_offer.png, docs/demo_weekly_results.png")
        if a.no_video:
            return 0
        with tempfile.TemporaryDirectory(prefix="truelift-video-") as tmp:
            res = subprocess.run(
                ["node", str(UI / "record_demo.js"), url, tmp, str(a.seconds)],
                cwd=UI,
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode:
                print(res.stdout, res.stderr)
                return res.returncode
            webm = Path(res.stdout.strip().splitlines()[-1])
            a.out.parent.mkdir(parents=True, exist_ok=True)
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", str(webm), "-c:v", "libx264", "-preset", "slow"]
            cmd += ["-crf", "28", "-pix_fmt", "yuv420p", "-r", "25", "-movflags", "+faststart", "-an", str(a.out)]
            subprocess.run(cmd, check=True)
    finally:
        server.terminate()
        server.wait(timeout=10)
    probe = imageio_ffmpeg.count_frames_and_secs(str(a.out))
    size = a.out.stat().st_size / 1e6
    print(f"wrote {a.out.relative_to(ROOT)}: {probe[1]:.0f} s, {size:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
