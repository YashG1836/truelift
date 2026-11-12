"""Check the uplift method on real randomised experiments (not the simulator).

    .venv/bin/python scripts/validate_uplift.py criteo   # Criteo incrementality tests (open download)
    .venv/bin/python scripts/validate_uplift.py mtlift   # Meituan MT-LIFT coupons (if you have it)

criteo: data/raw/criteo_uplift/criteo-research-uplift-v2.1.csv.gz, 14M users from ad
  incrementality tests (a random 15% were held out of advertising, like TrueLift's control
  group). 12 anonymised features f0..f11, treatment 0/1, labels visit and conversion.
  https://huggingface.co/datasets/criteo/criteo-uplift (CC BY-NC-SA 4.0)
mtlift: data/raw/mt_lift/train.csv + test.csv, Meituan food-delivery coupons, treatment 0..4.
  https://github.com/MTDJDSP/MT-LIFT (download links currently broken, see the repo's issues)

The same T-learner TrueLift uses ranks held-out users by predicted uplift; the Qini coefficient
scores the ranking on data it never saw (0 = no better than random). Writes reports/uplift_validation_<name>.json.
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

from truelift.model import qini_coefficient, qini_curve  # noqa: E402


def gbm(seed: int) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, max_leaf_nodes=63,
                                          min_samples_leaf=500, early_stopping=True, random_state=seed)


def score_arm(train, test, feats, arm, label, rng) -> dict:
    """T-learner for one treatment arm vs control, scored on the test rows."""
    c_tr, t_tr = train[train["treatment"] == 0], train[train["treatment"] == arm]
    m0 = gbm(0).fit(c_tr[feats], c_tr[label])
    m1 = gbm(1).fit(t_tr[feats], t_tr[label])
    te = test[test["treatment"].isin([0, arm])]
    treated = (te["treatment"] == arm).to_numpy()
    y = te[label].to_numpy()
    up = m1.predict_proba(te[feats])[:, 1] - m0.predict_proba(te[feats])[:, 1]
    frac, q, _ = qini_curve(up, treated, y, points=11)
    top30 = int(np.argmin(np.abs(frac - 0.3)))
    return {
        "label": label, "test_rows": int(len(te)), "share_treated": round(float(treated.mean()), 3),
        "rate_treated": round(float(y[treated].mean()), 5), "rate_control": round(float(y[~treated].mean()), 5),
        "qini_t_learner": round(qini_coefficient(up, treated, y), 3),
        "qini_random": round(qini_coefficient(rng.random(len(te)), treated, y), 3),
        # share of all the extra outcomes the campaign created that come from the top 30% by score
        "top30_share_of_total_lift": round(float(q[top30] / q[-1]), 3) if q[-1] > 0 else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", choices=["criteo", "mtlift"])
    ap.add_argument("--rows", type=int, default=3_000_000, help="training rows to sample")
    ap.add_argument("--data", type=Path, default=None)
    args = ap.parse_args()
    rng = np.random.default_rng(0)
    if args.dataset == "criteo":
        path = args.data or ROOT / "data/raw/criteo_uplift/criteo-research-uplift-v2.1.csv.gz"
        if not path.exists():
            print(f"missing {path}: download from https://huggingface.co/datasets/criteo/criteo-uplift")
            return 1
        df = pd.read_csv(path)
        split = rng.random(len(df)) < 0.7  # the file has no official split: 70% train, 30% test
        train, test = df[split], df[~split]
        labels, arms = ["visit", "conversion"], [1]
    else:
        base = args.data or ROOT / "data/raw/mt_lift"
        if not (base / "train.csv").exists():
            print(f"missing {base}/train.csv: see https://github.com/MTDJDSP/MT-LIFT")
            return 1
        train, test = pd.read_csv(base / "train.csv"), pd.read_csv(base / "test.csv")
        labels, arms = ["conversion"], sorted(int(t) for t in train["treatment"].unique() if t != 0)
    if len(train) > args.rows:
        train = train.sample(args.rows, random_state=0)
    feats = [c for c in train.columns if c.startswith("f")]
    out = {"dataset": args.dataset, "train_rows": int(len(train)), "results": []}
    for arm in arms:
        for label in labels:
            r = {"arm": arm, **score_arm(train, test, feats, arm, label, rng)}
            out["results"].append(r)
            print(r, flush=True)
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / f"reports/uplift_validation_{args.dataset}.json").write_text(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
