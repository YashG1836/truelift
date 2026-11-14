"""Golden test: the quick pipeline reproduces a committed snapshot, value by value.

The pipeline is deterministic, so an unintended change to the simulator, the model or the engine
fails here. An intended change re-records the snapshot in the same commit, which puts every
numerical change in front of the reviewer:

    python tasks.py golden        # re-run the quick pipeline and overwrite the snapshot

The comparison itself lives in scripts/compare_reports.py (also used by `tasks.py reproduce`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.compare_reports import diff

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests/golden/quick_evaluation.json"


def test_diff_helper_finds_changes():
    assert diff({"a": 1, "b": [1.0, 2.0]}, {"a": 1, "b": [1.0, 2.0000000001]}) == []
    assert diff({"a": 1}, {"a": 2}) == ["/a: 1 != 2"]
    assert diff({"a": {"meta": 1}}, {"a": {"meta": 2}}) == []
    assert diff({"a": 1}, {}) == ["/a: missing"]


@pytest.mark.slow
def test_quick_pipeline_matches_golden(quick_report):
    got = quick_report
    want = json.loads(GOLDEN.read_text(encoding="utf-8"))
    problems = diff(want, got)
    assert not problems, f"{len(problems)} differences from the golden snapshot:\n" + "\n".join(problems[:60])
