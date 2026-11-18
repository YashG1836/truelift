"""Record the guided demo as a captioned video for the pitch (docs/pitch/demo.mp4, plan A03 4.4)
and take the README's images (docs/img/: the animated tour, four phone screens, three pictures).

    python scripts/make_video.py                  # after `python tasks.py export`
    python scripts/make_video.py --seconds 11     # reading time per step (default 12)
    python scripts/make_video.py --no-video       # the README images only (python tasks.py screenshots)
    python scripts/make_video.py --no-video --url https://yashg1836.github.io/truelift/

Serves the exported site (site/) on a free local port, or uses --url, and lets Playwright's
Chromium walk through the demo with generic restaurant names (decision D5: the deck, the video and
the README do not show real brand names). tests/ui/screenshots.js takes the images; the guided
demo's frames become docs/img/tour.gif, and the recording becomes H.264 MP4, both with the ffmpeg
binary that imageio-ffmpeg ships (uv group `media`). The tour's own captions explain every step, so
no voice is needed. Every image and the recording show simulated customers, orders and profits,
and say so on screen.
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
IMG = ROOT / "docs" / "img"
UI = ROOT / "tests" / "ui"
GIF_SECONDS = 3.5  # each guided-demo step in the animation
GIF_WIDTH = 900  # pixels; GitHub shows the README about this wide


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


def make_gif(frames: list[Path], out: Path, ffmpeg: str) -> None:
    """Loop the guided-demo frames as one GIF with a shared palette, so GitHub plays it in the README.
    The concat list repeats the last frame because ffmpeg ignores the duration of the final entry."""
    with tempfile.TemporaryDirectory(prefix="truelift-gif-") as tmp:
        lst = Path(tmp) / "frames.txt"
        lines = []
        for f in frames:
            lines += [f"file '{f.as_posix()}'", f"duration {GIF_SECONDS}"]
        lines.append(f"file '{frames[-1].as_posix()}'")
        lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
        vf = (
            f"scale={GIF_WIDTH}:-1:flags=lanczos,split[a][b];"
            "[a]palettegen=max_colors=192:stats_mode=full[p];[b][p]paletteuse=dither=none"
        )
        cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst)]
        cmd += ["-vf", vf, "-fps_mode", "vfr", "-loop", "0", str(out)]
        subprocess.run(cmd, check=True)


def readme_images(url: str, ffmpeg: str) -> None:
    IMG.mkdir(parents=True, exist_ok=True)
    for old in IMG.glob("tour_*.png"):
        old.unlink()
    subprocess.run(["node", str(UI / "screenshots.js"), url, str(IMG)], cwd=UI, check=True)
    frames = sorted(IMG.glob("tour_*.png"))
    if not frames:
        raise RuntimeError("screenshots.js wrote no guided-demo frames")
    make_gif(frames, IMG / "tour.gif", ffmpeg)
    for f in frames:
        f.unlink()
    for f in sorted(IMG.iterdir()):
        print(f"wrote {f.relative_to(ROOT).as_posix()}: {f.stat().st_size / 1e3:.0f} kB")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seconds", type=float, default=12.0, help="reading time per guided-demo step")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--no-video", action="store_true", help="only the README images")
    ap.add_argument("--url", help="use this published site instead of serving site/")
    a = ap.parse_args()
    if not a.url and not (SITE / "index.html").exists():
        print("No site/ found: run `python tasks.py export` first, or pass --url.")
        return 1
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    server = None
    if a.url:
        base = a.url.split("#")[0]
    else:
        port = free_port()
        server = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(SITE)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        base = f"http://127.0.0.1:{port}/"
    try:
        wait_for(base.rstrip("/") + "/data/config.json")
        url = base + "#names=generic"
        readme_images(url, ffmpeg)
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
            cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", str(webm), "-c:v", "libx264", "-preset", "slow"]
            cmd += ["-crf", "28", "-pix_fmt", "yuv420p", "-r", "25", "-movflags", "+faststart", "-an", str(a.out)]
            subprocess.run(cmd, check=True)
    finally:
        if server:
            server.terminate()
            server.wait(timeout=10)
    probe = imageio_ffmpeg.count_frames_and_secs(str(a.out))
    size = a.out.stat().st_size / 1e6
    print(f"wrote {a.out.relative_to(ROOT)}: {probe[1]:.0f} s, {size:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
