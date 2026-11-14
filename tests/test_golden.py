"""Golden test: the quick pipeline reproduces a committed snapshot, value by value.

The pipeline is deterministic, so an unintended change to the simulator, the model or the engine
fails here. An intended change re-records the snapshot in the same commit, which puts every
numerical change in front of the reviewer:

    python tasks.py golden        # re-run the quick pipeline and overwrite the snapshot

The comparison itself lives in scripts/compare_reports.py (also used by `tasks.py reproduce`).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.compare_reports import diff

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests/golden/quick_evaluation.json"


def run_quick(out_dir: Path) -> dict:
    cmd = [
        sys.executable,
        str(ROOT / "scripts/run_pipeline.py"),
        "--quick",
        "--out",
        str(out_dir),
        "--model-out",
        str(out_dir / "model.pkl"),
    ]
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
