"""Offline demo: the static site as a folder and a zip that work with no internet and no install.

    python scripts/build_offline.py          # needs site/ (python tasks.py export) -> dist/truelift-offline.zip

Two ways to open it, both offline:
  1. Double-click index.html. Browsers refuse fetch() on file:// pages, so every data file is also
     written as a small script (data/x.js registers data/x.json in window.TL_FILES), which the page
     loads instead. The font is embedded in the stylesheet for the same reason.
  2. Run serve.py (or serve.bat / serve.sh): a local web server on 127.0.0.1, then the browser opens.

Never includes error tracking or anything that calls out; the page has no third-party resources.
"""

from __future__ import annotations

import base64
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
DIST = ROOT / "dist"
OUT = DIST / "truelift-offline"

SERVE_PY = '''"""Start the TrueLift demo on this computer (no internet needed) and open it in the browser."""
import functools
import http.server
import socketserver
import sys
import threading
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765

handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(HERE))
handler.log_message = lambda *a: None
with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), handler) as httpd:
    url = f"http://127.0.0.1:{PORT}/"
    print(f"TrueLift demo running at {url}  (press Ctrl+C to stop)")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
'''

README = """TrueLift offline demo
=====================

Simulated data: restaurant names and listing details are real public 2019 Zomato listings;
customers, orders and profits are simulated.

Open it in either way, with no internet:
  1. Double-click index.html (Chrome, Edge or Firefox).
  2. Or run serve.bat (Windows) / serve.sh (macOS, Linux), or `python serve.py`, which opens
     http://127.0.0.1:8765/ in your browser.

The live version (any design, any restaurant) needs the service: see the repository README.
Font: Figtree, SIL Open Font License 1.1 (static/fonts/OFL.txt).
"""


def embed_fonts(css: str, fonts: Path) -> str:
    """url(fonts/x.woff2) -> data: URI, so the font loads from a file:// page too."""

    def repl(m: re.Match) -> str:
        data = base64.b64encode((fonts / m.group(1)).read_bytes()).decode("ascii")
        return f"url(data:font/woff2;base64,{data})"

    return re.sub(r"url\(fonts/([\w.-]+\.woff2)\)", repl, css)


def main() -> int:
    if not (SITE / "data" / "restaurants.json").exists():
        print("site/ is missing or incomplete: run `python tasks.py export` first.")
        return 1
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(SITE, OUT)
    n = 0
    for f in sorted((OUT / "data").rglob("*.json")):
        rel = f.relative_to(OUT / "data").as_posix()
        body = f.read_text(encoding="utf-8")
        json.loads(body)  # refuse to wrap a damaged file
        f.with_suffix(".js").write_text(
            f"(window.TL_FILES=window.TL_FILES||{{}})[{json.dumps(rel)}]={body};\n", encoding="utf-8"
        )
        n += 1
    css = OUT / "static" / "style.css"
    css.write_text(embed_fonts(css.read_text(encoding="utf-8"), OUT / "static" / "fonts"), encoding="utf-8")
    html = OUT / "index.html"
    page = re.sub(r'<link rel="preload"[^>]*>\n?', "", html.read_text(encoding="utf-8"))
    html.write_text(page, encoding="utf-8")
    (OUT / "serve.py").write_text(SERVE_PY, encoding="utf-8")
    (OUT / "serve.bat").write_text('@echo off\r\ncd /d "%~dp0"\r\npython serve.py %*\r\n', encoding="utf-8")
    (OUT / "serve.sh").write_text('#!/bin/sh\ncd "$(dirname "$0")"\nexec python3 serve.py "$@"\n', encoding="utf-8")
    (OUT / "README.txt").write_text(README, encoding="utf-8")
    zpath = DIST / "truelift-offline.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(OUT.rglob("*")):
            if f.is_file():
                info = zipfile.ZipInfo.from_file(f, f"truelift-offline/{f.relative_to(OUT).as_posix()}")
                if f.name == "serve.sh":
                    info.external_attr = 0o755 << 16
                z.writestr(info, f.read_bytes(), zipfile.ZIP_DEFLATED)
    print(f"{n} data files wrapped; folder {OUT}; zip {zpath} ({zpath.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
