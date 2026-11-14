"""One entry point for every routine job, the same on Windows, macOS and Linux.

    python tasks.py setup              install the pinned environment (+ the browser for UI tests)
    python tasks.py test [--all]       fast tests (about 20 s); --all adds golden and slow checks
    python tasks.py lint               ruff check, ruff format --check, pyright
    python tasks.py pipeline [--quick] simulate, train, evaluate -> reports/ and the model (~10 min)
    python tasks.py sensitivity        eight assumptions low and high -> reports/sensitivity.json (~5 min)
    python tasks.py benchmark          uplift learners against the truth -> reports/learner_benchmark.json
    python tasks.py experiments [name] the experiments behind the write-up's claims -> reports/exp_*.json
    python tasks.py latency            time the live service over HTTP -> reports/latency.json
    python tasks.py serve              live service and page at http://localhost:8000
    python tasks.py export [ids...]    static demo -> site/ (default: the demo restaurants)
    python tasks.py reproduce [--quick]  re-run the pipeline in a temp folder, compare with the
                                       committed numbers (--quick: with the golden snapshot)
    python tasks.py golden             re-record the golden snapshot after an intended change
    python tasks.py docker             build the image and run it on port 8000

Uses `uv run` when uv is installed; otherwise the Python running this file (so an activated
virtual environment with requirements-dev.txt works too). Standard library only.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UI = ROOT / "tests" / "ui"
# The restaurants on the public demo (see CLAUDE.md); 233 Burger King opens first.
DEMO_RESTAURANTS = ["233", "248", "17", "142", "191", "273", "84", "172", "57", "146", "283", "31"]


def py() -> list[str]:
    return ["uv", "run", "python"] if shutil.which("uv") else [sys.executable]


def run(cmd: list[str], **kw) -> int:
    print("+ " + " ".join(cmd), flush=True)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", **kw.pop("env", {})}
    return subprocess.call(cmd, cwd=kw.pop("cwd", ROOT), env=env, **kw)


def npm() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def npx() -> str:
    return "npx.cmd" if os.name == "nt" else "npx"


def setup(a) -> int:
    if shutil.which("uv"):
        rc = run(["uv", "sync", "--frozen"])
    else:
        rc = run([sys.executable, "-m", "pip", "install", "-r", "requirements-dev.txt"])
    if rc or a.no_browser:
        return rc
    if not shutil.which(npm()):
        print("Node.js not found: skipping the browser tests' setup (install Node 20+ to run them).")
        return 0
    return run([npm(), "ci"], cwd=UI) or run([npx(), "playwright", "install", "chromium"], cwd=UI)


def test(a) -> int:
    marks = [] if a.all else ["-m", "not slow"]
    return run([*py(), "-m", "pytest", "-q", *marks, *a.pytest_args])


def lint(a) -> int:
    tool = ["uv", "run"] if shutil.which("uv") else []
    return (
        run([*tool, "ruff", "check", "."]) or run([*tool, "ruff", "format", "--check", "."]) or run([*tool, "pyright"])
    )


def pipeline(a) -> int:
    return run([*py(), "scripts/run_pipeline.py", *(["--quick"] if a.quick else [])])


def serve(a) -> int:
    return run([*py(), "-m", "uvicorn", "truelift.api:app", "--host", a.host, "--port", str(a.port)])


def export(a) -> int:
    return run([*py(), "scripts/export_static.py", *(a.ids or DEMO_RESTAURANTS)])


def sensitivity(a) -> int:
    return run([*py(), "scripts/sensitivity.py", "--workers", str(a.workers)])


def benchmark(a) -> int:
    return run([*py(), "scripts/benchmark_learners.py", "--workers", str(a.workers)])


def experiments(a) -> int:
    return run([*py(), "scripts/experiments.py", a.name, *(["--quick"] if a.quick else [])])


def latency(a) -> int:
    return run([*py(), "scripts/bench_latency.py"])


def reproduce(a) -> int:
    with tempfile.TemporaryDirectory(prefix="truelift-reproduce-") as tmp:
        out = Path(tmp)
        args = ["--out", str(out), "--model-out", str(out / "model.pkl")]
        rc = run([*py(), "scripts/run_pipeline.py", *(["--quick"] if a.quick else []), *args])
        if rc:
            return rc
        want = ROOT / ("tests/golden/quick_evaluation.json" if a.quick else "reports")
        got = out / "evaluation.json" if a.quick else out
        return run([*py(), "scripts/compare_reports.py", str(want), str(got)])


def golden(a) -> int:
    with tempfile.TemporaryDirectory(prefix="truelift-golden-") as tmp:
        out = Path(tmp)
        rc = run(
            [*py(), "scripts/run_pipeline.py", "--quick", "--out", str(out), "--model-out", str(out / "model.pkl")]
        )
        if rc:
            return rc
        shutil.copyfile(out / "evaluation.json", ROOT / "tests/golden/quick_evaluation.json")
    print("Golden snapshot re-recorded; commit it together with the change that moved the numbers.")
    return 0


def docker(a) -> int:
    return run(["docker", "build", "-t", "truelift", "."]) or run(
        ["docker", "run", "--rm", "-p", f"{a.port}:8000", "truelift"]
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="task", required=True)
    p = sub.add_parser("setup")
    p.add_argument("--no-browser", action="store_true", help="skip Node and Chromium for the UI tests")
    p.set_defaults(fn=setup)
    p = sub.add_parser("test")
    p.add_argument("--all", action="store_true", help="include the slow checks (golden pipeline)")
    p.add_argument("pytest_args", nargs="*", help="extra arguments for pytest")
    p.set_defaults(fn=test)
    sub.add_parser("lint").set_defaults(fn=lint)
    p = sub.add_parser("pipeline")
    p.add_argument("--quick", action="store_true")
    p.set_defaults(fn=pipeline)
    for name, fn in (("sensitivity", sensitivity), ("benchmark", benchmark)):
        p = sub.add_parser(name)
        p.add_argument("--workers", type=int, default=3, help="runs at a time (each needs 1-2 GB)")
        p.set_defaults(fn=fn)
    p = sub.add_parser("experiments")
    p.add_argument("name", nargs="?", default="all")
    p.add_argument("--quick", action="store_true")
    p.set_defaults(fn=experiments)
    sub.add_parser("latency").set_defaults(fn=latency)
    p = sub.add_parser("serve")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(fn=serve)
    p = sub.add_parser("export")
    p.add_argument("ids", nargs="*", help="restaurant ids (default: the demo set)")
    p.set_defaults(fn=export)
    p = sub.add_parser("reproduce")
    p.add_argument("--quick", action="store_true")
    p.set_defaults(fn=reproduce)
    sub.add_parser("golden").set_defaults(fn=golden)
    p = sub.add_parser("docker")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(fn=docker)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
