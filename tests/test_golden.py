"""Golden test: the quick pipeline reproduces a committed snapshot, value by value.

The pipeline is deterministic, so an unintended change to the simulator, the model or the engine
fails here. An intended change re-records the snapshot in the same commit, which puts every
numerical change in front of the reviewer:

    python tasks.py golden        # re-run the quick pipeline and overwrite the snapshot
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests/golden/quick_evaluation.json"
IGNORED_KEYS = {"meta"}  # run metadata (time, commit, versions) legitimately changes


def diff(want, got, path: str = "", out: list | None = None, rel: float = 1e-6) -> list[str]:
    """List every difference between two JSON trees (floats compared with a small tolerance)."""
    out = [] if out is None else out
    if isinstance(want, dict) and isinstance(got, dict):
        for k in sorted(set(want) | set(got)):
            if k in IGNORED_KEYS:
                continue
            if k not in want or k not in got:
                out.append(f"{path}/{k}: {'missing' if k not in got else 'unexpected'}")
            else:
                diff(want[k], got[k], f"{path}/{k}", out, rel)
    elif isinstance(want, list) and isinstance(got, list):
        if len(want) != len(got):
            out.append(f"{path}: length {len(want)} != {len(got)}")
        for i, (a, b) in enumerate(zip(want, got, strict=False)):  # a length mismatch is reported above
            diff(a, b, f"{path}[{i}]", out, rel)
    elif isinstance(want, bool) or isinstance(got, bool) or isinstance(want, str) or want is None:
        if want != got:
            out.append(f"{path}: {want!r} != {got!r}")
    elif isinstance(want, (int, float)) and isinstance(got, (int, float)):
        if not math.isclose(float(want), float(got), rel_tol=rel, abs_tol=1e-9):
            out.append(f"{path}: {want} != {got}")
    elif want != got:
        out.append(f"{path}: {want!r} != {got!r}")
    return out


def run_quick(out_dir: Path) -> dict:
    cmd = [sys.executable, str(ROOT / "scripts/run_pipeline.py"), "--quick", "--out", str(out_dir),
           "--model-out", str(out_dir / "model.pkl")]
    subprocess.run(cmd, check=True, cwd=ROOT, capture_output=True)
    return json.loads((out_dir / "evaluation.json").read_text(encoding="utf-8"))


def test_diff_helper_finds_changes():
    assert diff({"a": 1, "b": [1.0, 2.0]}, {"a": 1, "b": [1.0, 2.0000000001]}) == []
    assert diff({"a": 1}, {"a": 2}) == ["/a: 1 != 2"]
    assert diff({"a": {"meta": 1}}, {"a": {"meta": 2}}) == []
    assert diff({"a": 1}, {}) == ["/a: missing"]


@pytest.mark.slow
def test_quick_pipeline_matches_golden(tmp_path):
    got = run_quick(tmp_path)
    want = json.loads(GOLDEN.read_text(encoding="utf-8"))
    problems = diff(want, got)
    assert not problems, f"{len(problems)} differences from the golden snapshot:\n" + "\n".join(problems[:60])
