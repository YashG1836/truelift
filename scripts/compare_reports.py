"""Compare two pipeline outputs value by value; run metadata is ignored.

    python scripts/compare_reports.py reports/evaluation.json /tmp/run/evaluation.json
    python scripts/compare_reports.py reports /tmp/run          # every .json and .csv in both folders

Floats match when they agree to a relative 1e-6. Exit code 0 when everything matches, 1 with the
list of differences otherwise. The golden test and `python tasks.py reproduce` both use it, so
"the numbers reproduce" means the same thing everywhere.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd

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


def diff_csv(want: Path, got: Path, rel: float = 1e-6) -> list[str]:
    a, b = pd.read_csv(want), pd.read_csv(got)
    if list(a.columns) != list(b.columns) or len(a) != len(b):
        return [f"{want.name}: shape or columns differ ({a.shape} vs {b.shape})"]
    out = []
    for col in a.columns:
        x, y = a[col], b[col]
        if pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y):
            for i, (u, v) in enumerate(zip(x, y, strict=True)):
                both_nan = pd.isna(u) and pd.isna(v)
                if not both_nan and not math.isclose(float(u), float(v), rel_tol=rel, abs_tol=1e-9):
                    out.append(f"{want.name}[{i}].{col}: {u} != {v}")
        else:
            for i, (u, v) in enumerate(zip(x.astype(str), y.astype(str), strict=True)):
                if u != v:
                    out.append(f"{want.name}[{i}].{col}: {u!r} != {v!r}")
    return out


def compare(want: Path, got: Path) -> list[str]:
    """Differences between two files, or between the .json and .csv files of two folders."""
    want, got = Path(want), Path(got)
    if want.is_dir():
        out = []
        for f in sorted(want.iterdir()):
            if f.suffix in (".json", ".csv") and (got / f.name).exists():
                out += compare(f, got / f.name)
        return out
    if want.suffix == ".csv":
        return diff_csv(want, got)
    return diff(
        json.loads(want.read_text(encoding="utf-8")), json.loads(got.read_text(encoding="utf-8")), f"{want.name}:"
    )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    problems = compare(Path(argv[0]), Path(argv[1]))
    if problems:
        print(f"{len(problems)} differences:")
        print("\n".join(problems[:200]))
        return 1
    print("Identical (run metadata ignored).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
