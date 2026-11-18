"""Build the submission files from the frozen reports: the IEEE-format report and the presentation.

    python submission/src/build.py           # both
    python submission/src/build.py report    # TrueLift_Report.pdf (needs tectonic: brew install tectonic)
    python submission/src/build.py deck      # TrueLift_Presentation.pdf and .html (needs Google Chrome or Chromium)

No number is typed by hand. Every number is computed from reports/ by the code of
scripts/check_claims.py (the claims ledger docs/claims.yml), and every table is read from the
generated tables of docs/method_and_evidence.md, which scripts/render_tables.py --check keeps equal to
reports/. So the report and the slides say exactly what the repository says. Intermediate files go to
submission/src/build/ (not committed).
"""

from __future__ import annotations

import base64
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE.parent
BUILD = HERE / "build"
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

from check_claims import fmt, namespace  # noqa: E402
from render_tables import lakh  # noqa: E402

IMAGES = ["owner_forecast", "owner_better", "owner_otp", "owner_result", "who_sees", "problem", "evidence"]
FONTS = ["figtree-latin-400", "figtree-latin-500", "figtree-latin-600", "figtree-latin-700"]


def numbers() -> dict[str, str]:
    """Every claim of the ledger, formatted as the documents print it, plus a few values for charts."""
    ns = namespace()
    ledger = yaml.safe_load((ROOT / "docs/claims.yml").read_text(encoding="utf-8"))
    n = {c["id"]: fmt(eval(c["expr"], {"__builtins__": {}, **ns}), c.get("format", "plain")) for c in ledger["claims"]}  # noqa: S307
    ev = json.loads((ROOT / "reports/evaluation.json").read_text(encoding="utf-8"))["main"]["policies"]
    lat = json.loads((ROOT / "reports/latency.json").read_text(encoding="utf-8"))
    cols = {"bl": "today_blanket", "rule": "rule_new_customers", "tl": "truelift"}
    for k, p in cols.items():
        q = ev[p]
        n[f"{k}_market"] = lakh(q["restaurant_profit_change"], sign=True)
        n[f"{k}_discount"] = lakh(q["customer_savings"])
        n[f"{k}_commission"] = lakh(q["zomato_commission_change"], sign=True)
        n[f"{k}_own"] = lakh(q["own_offer_profit_effect"], sign=True)
        n[f"{k}_pay"] = str(q["offers_that_pay"])
        n[f"{k}_with"] = str(q["restaurants_with_offer"])
        n[f"{k}_lose"] = str(q["offers_that_lose"])
    # bar lengths for the slides, as a share of the longest bar in each chart
    for metric in ("restaurant_profit_change", "customer_savings", "zomato_commission_change"):
        top = max(ev[p][metric] for p in cols.values())
        for k, p in cols.items():
            n[f"w_{k}_{metric}"] = f"{100 * ev[p][metric] / top:.1f}"
    for k, p in cols.items():
        n[f"w_{k}_pay"] = f"{100 * ev[p]['offers_that_pay'] / ev[p]['restaurants_with_offer']:.1f}"
    n["lat_serve_p50"] = f"{lat['serve_sequential']['p50_ms']:.1f}"
    n["lat_serve_p95"] = f"{lat['serve_sequential']['p95_ms']:.1f}"
    n["lat_serve_p99"] = f"{lat['serve_sequential']['p99_ms']:.1f}"
    n["lat_inside_p50"] = f"{lat['serve_sequential']['server_side']['p50_ms']:.2f}"
    n["lat_inside_p95"] = f"{lat['serve_sequential']['server_side']['p95_ms']:.2f}"
    n["lat_inside_p99"] = f"{lat['serve_sequential']['server_side']['p99_ms']:.2f}"
    n["lat_8_p50"] = f"{lat['serve_8_threads']['p50_ms']:.1f}"
    n["lat_8_p95"] = f"{lat['serve_8_threads']['p95_ms']:.1f}"
    n["lat_8_p99"] = f"{lat['serve_8_threads']['p99_ms']:.1f}"
    n["lat_quote_p50"] = f"{lat['quote_sequential']['p50_ms']:.0f}"
    n["lat_quote_p95"] = f"{lat['quote_sequential']['p95_ms']:.0f}"
    n["lat_quote_p99"] = f"{lat['quote_sequential']['p99_ms']:.0f}"
    n["lat_cpus"] = str(lat["hardware"]["logical_cpus"])
    # the money of one order (truelift/economics.py), for the report's first table
    ex = ns["ex"]
    for k, o in (("full", ex["per_order_full"]), ("disc", ex["per_order_discounted"])):
        for f in (
            "basket",
            "discount",
            "commission",
            "gst_on_commission",
            "food_cost",
            "restaurant_profit",
            "zomato_gross",
        ):
            v = o[f]
            n[f"ord_{k}_{f}"] = f"₹{v:,.2f}" if v != round(v) else f"₹{v:,.0f}"
    n["claims_count"] = str(len(ledger["claims"]))
    # the weekly measurement table, for the slides (coverage as plain numbers for bar heights)
    _, mea = md_table("measurement-table")
    for r in mea:
        wk = r[0].split()[0]
        n[f"h_cov_{wk}"] = r[1].rstrip("%")
        n[f"keep_{wk}_text"] = r[5]
    return n


def md_table(name: str) -> tuple[list[str], list[list[str]]]:
    """A generated table of docs/method_and_evidence.md: header and rows."""
    text = (ROOT / "docs/method_and_evidence.md").read_text(encoding="utf-8")
    m = re.search(rf"<!-- BEGIN:{name} -->\n(.*?)<!-- END:{name} -->", text, re.S)
    if not m:
        raise SystemExit(f"table {name} not found in docs/method_and_evidence.md")
    lines = [ln.strip().strip("|") for ln in m.group(1).strip().splitlines()]
    rows = [[c.strip() for c in ln.split("|")] for ln in lines]
    return rows[0], rows[2:]


# ---------------------------------------------------------------- report (LaTeX, IEEEtran)


def tex(s: str) -> str:
    s = s.replace("\\", r"\textbackslash{}")
    for a, b in (("&", r"\&"), ("%", r"\%"), ("#", r"\#"), ("_", r"\_"), ("$", r"\$")):
        s = s.replace(a, b)
    s = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", s)
    s = re.sub(r'"(.+?)"', r"``\1''", s)
    return s


def tex_rows(rows: list[list[str]], keep: list[int] | None = None, in_lakh: bool = False) -> str:
    """Table rows for LaTeX; in_lakh drops '₹' and ' lakh' from money cells (the caption gives the unit)."""
    out = []
    for r in rows:
        cells = [r[i] for i in keep] if keep else r
        if in_lakh:
            cells = [cells[0]] + [c.replace("₹", "").replace(" lakh", "") for c in cells[1:]]
        out.append(" & ".join(tex(c) for c in cells) + r" \\")
    return "\n".join(out)


def write_tex_inputs(n: dict[str, str]) -> None:
    lines = [r"% Generated by submission/src/build.py from reports/. Do not edit."]
    for k, v in sorted(n.items()):
        lines.append(rf"\expandafter\def\csname n@{k}\endcsname{{{tex(v)}}}")
    lines.append(r"\newcommand{\V}[1]{\ifcsname n@#1\endcsname\csname n@#1\endcsname\else\errmessage{no number #1}\fi}")
    # tables
    _, res = md_table("results-table")
    lines.append(r"\newcommand{\TabResults}{" + tex_rows(res, in_lakh=True) + "}")
    _, mea = md_table("measurement-table")
    lines.append(r"\newcommand{\TabMeasurement}{" + tex_rows(mea) + "}")
    _, real = md_table("realdata-table")
    lines.append(r"\newcommand{\TabRealData}{" + tex_rows(real) + "}")
    _, sce = md_table("scenario-table")
    lines.append(r"\newcommand{\TabScenarios}{" + tex_rows(sce, keep=[0, 1, 2, 3]) + "}")
    # chart coordinates: the two baselines in grey, TrueLift in blue
    ev = json.loads((ROOT / "reports/evaluation.json").read_text(encoding="utf-8"))["main"]["policies"]
    base = (("Blanket", "today_blanket"), ("Rule", "rule_new_customers"))
    for name, metric in (("Market", "restaurant_profit_change"), ("Discount", "customer_savings")):
        coords = " ".join(f"({lbl},{ev[p][metric] / 1e5:.2f})" for lbl, p in base)
        lines.append(rf"\newcommand{{\Coord{name}Base}}{{{coords}}}")
        lines.append(rf"\newcommand{{\Coord{name}TL}}{{(TrueLift,{ev['truelift'][metric] / 1e5:.2f})}}")
    errs = {"own": [], "model": [], "comb": [], "cov": []}
    for r in mea:
        wk = int(r[0].split()[0])
        errs["cov"].append(f"({wk},{r[1].rstrip('%')})")
        errs["own"].append(f"({wk},{r[2].lstrip('₹').replace(',', '')})")
        errs["model"].append(f"({wk},{r[3].lstrip('₹').replace(',', '')})")
        errs["comb"].append(f"({wk},{r[4].lstrip('₹').replace(',', '')})")
    for k, v in errs.items():
        lines.append(rf"\newcommand{{\CoordErr{k}}}{{{' '.join(v)}}}")
    (BUILD / "numbers.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_report(n: dict[str, str]) -> Path:
    tectonic = shutil.which("tectonic")
    if not tectonic:
        raise SystemExit("tectonic not found: brew install tectonic (or see https://tectonic-typesetting.github.io)")
    (BUILD / "img").mkdir(parents=True, exist_ok=True)
    for name in IMAGES:
        shutil.copyfile(ROOT / "docs/img" / f"{name}.png", BUILD / "img" / f"{name}.png")
    write_tex_inputs(n)
    shutil.copyfile(HERE / "report.tex", BUILD / "report.tex")
    subprocess.run([tectonic, "-X", "compile", "--keep-logs", "report.tex"], cwd=BUILD, check=True)
    out = OUT / "TrueLift_Report.pdf"
    shutil.copyfile(BUILD / "report.pdf", out)
    return out


# ---------------------------------------------------------------- presentation (HTML -> PDF)


def data_uri(path: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def fill_deck(n: dict[str, str]) -> str:
    page = (HERE / "deck.html").read_text(encoding="utf-8")
    # the demo's QR code, as made by scripts/make_deck.py (qrcode) for the pitch deck
    qr = re.search(r'<svg class="qr".*?</svg>', (ROOT / "docs/pitch/deck.html").read_text(encoding="utf-8"), re.S)

    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key == "qr":
            if not qr:
                raise SystemExit("no QR code in docs/pitch/deck.html: run python tasks.py deck first")
            return qr.group(0)
        if key.startswith("img:"):
            return data_uri(ROOT / "docs/img" / f"{key[4:]}.png", "image/png")
        if key.startswith("font:"):
            return data_uri(ROOT / "truelift/static/fonts" / f"{key[5:]}.woff2", "font/woff2")
        if key not in n:
            raise SystemExit(f"deck.html asks for {{{{{key}}}}}, which no report gives")
        return html.escape(n[key])

    return re.sub(r"\{\{([a-z0-9_:\-]+)\}\}", sub, page)


def chrome() -> str:
    for c in (
        os.environ.get("CHROME", ""),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        shutil.which("google-chrome") or "",
        shutil.which("chromium") or "",
        shutil.which("chromium-browser") or "",
    ):
        if c and Path(c).exists():
            return c
    raise SystemExit("Google Chrome or Chromium not found (set CHROME=/path/to/chrome)")


def build_deck(n: dict[str, str]) -> Path:
    BUILD.mkdir(parents=True, exist_ok=True)
    filled = fill_deck(n)
    (OUT / "TrueLift_Presentation.html").write_text(filled, encoding="utf-8")
    src = BUILD / "deck.html"
    src.write_text(filled, encoding="utf-8")
    pdf = OUT / "TrueLift_Presentation.pdf"
    cmd = [
        chrome(),
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        "--virtual-time-budget=8000",
        f"--print-to-pdf={pdf}",
        src.as_uri(),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return pdf


def main() -> int:
    what = sys.argv[1:] or ["report", "deck"]
    BUILD.mkdir(parents=True, exist_ok=True)
    n = numbers()
    if "report" in what:
        print("wrote", build_report(n).relative_to(ROOT))
    if "deck" in what:
        print("wrote", build_deck(n).relative_to(ROOT), "and submission/TrueLift_Presentation.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
