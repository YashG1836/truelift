"""Check the uplift method on real randomised data: Meituan's MT-LIFT food-delivery coupons.

    .venv/bin/python scripts/validate_mtlift.py [--rows 1000000]

Needs data/raw/mt_lift/train.csv and test.csv (github.com/MTDJDSP/MT-LIFT; the Google Drive
link needs a sign-in, so download by hand). Columns: f0..f98 features, treatment 0 (control) to 4
(coupon types), click, conversion. Coupons were assigned at random, so a T-learner's ranking can be
scored with the Qini coefficient on the test file: 0 = no better than random.
Writes reports/mtlift_validation.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from truelift.model import qini_coefficient  # noqa: E402

DATA = ROOT / "data/raw/mt_lift"


def gbm(seed: int) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, max_leaf_nodes=63,
                                          min_samples_leaf=500, early_stopping=True, random_state=seed)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=1_000_000, help="training rows to sample")
    ap.add_argument("--data", type=Path, default=DATA)
    args = ap.parse_args()
    if not (args.data / "train.csv").exists():
        print(f"missing {args.data}/train.csv: download MT-LIFT from github.com/MTDJDSP/MT-LIFT")
        return 1
    train = pd.read_csv(args.data / "train.csv")
    test = pd.read_csv(args.data / "test.csv")
    if len(train) > args.rows:
        train = train.sample(args.rows, random_state=0)
    feats = [c for c in train.columns if c.startswith("f")]
    out = {"train_rows": len(train), "test_rows": len(test), "arms": {}}
    ctrl_tr, ctrl_te = train[train["treatment"] == 0], test[test["treatment"] == 0]
    m0 = gbm(0).fit(ctrl_tr[feats], ctrl_tr["conversion"])
    rng = np.random.default_rng(0)
    for arm in sorted(t for t in train["treatment"].unique() if t != 0):
        tr = train[train["treatment"] == arm]
        m1 = gbm(int(arm)).fit(tr[feats], tr["conversion"])
        te = pd.concat([test[test["treatment"] == arm], ctrl_te])
        treated = (te["treatment"] == arm).to_numpy()
        score = m1.predict_proba(te[feats])[:, 1] - m0.predict_proba(te[feats])[:, 1]
        y = te["conversion"].to_numpy()
        out["arms"][int(arm)] = {
            "test_rows": int(len(te)),
            "conversion_treated": round(float(y[treated].mean()), 4),
            "conversion_control": round(float(y[~treated].mean()), 4),
            "qini_t_learner": round(qini_coefficient(score, treated, y), 3),
            "qini_random": round(qini_coefficient(rng.random(len(te)), treated, y), 3),
        }
        print(f"arm {arm}: {out['arms'][int(arm)]}", flush=True)
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports/mtlift_validation.json").write_text(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
