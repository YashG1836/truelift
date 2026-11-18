"""Check the uplift method on real randomised experiments (not the simulator).

    python scripts/get_data.py criteo hillstrom        # download and verify the data (data/raw/)
    python scripts/validate_uplift.py hillstrom        # about 2 minutes
    python scripts/validate_uplift.py criteo           # about 30 minutes, 4 GB of memory

criteo: 14 million users of Criteo's advertising incrementality tests; a random 15% were held out
  of advertising, like TrueLift's control group. 12 anonymised features, outcomes visit and
  conversion. CC BY-NC-SA 4.0. https://huggingface.co/datasets/criteo/criteo-uplift
hillstrom: 64,000 customers of a retailer who bought in the last year, e-mailed at random with
  men's merchandise, women's merchandise, or nothing; outcomes visit, conversion and spend in
  dollars over two weeks (the only public test here with a money outcome). Kevin Hillstrom,
  MineThatData E-Mail Analytics challenge, 2008.

For each dataset, treatment arm and outcome, held-out customers are ranked five ways:
  random; response model (the predicted outcome if treated: the usual shortcut, which finds
  people likely to buy anyway); S-learner (one model with the treatment as an input); T-learner
  (one model per group, TrueLift's method); X-learner (Kunzel et al. 2019). Every model is a
  gradient-boosted tree with the same settings.
Measures, on customers no model saw:
  - share of the campaign's total incremental outcome found in the top 30% of the ranking
    (random: about 30%);
  - incremental outcome per customer in that top 30%, against the average;
  - normalised area under the Qini curve, two ways: this project's definition (area between the
    curve and the random line divided by the campaign's total gain) and scikit-uplift's
    `qini_auc_score` (divided by the area a perfect ranking would have), so the figure can be
    compared with published results (audit TL-039).
Intervals: 200 bootstrap resamples of the test set (5th to 95th percentile) on the first split,
and the spread over five random 70/30 splits (audit TL-040).
Writes reports/uplift_validation_<dataset>.json.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from get_data import DATA, sha256  # noqa: E402

RANKINGS = ("random", "response", "s_learner", "t_learner", "x_learner")
BINS = 1000  # the ranking is cut into 1,000 equal groups; 30% = the first 300
TOP = 0.3
BOOT = 200
SPLITS = 5
ABOUT = {
    "criteo": {
        "what": "Criteo advertising incrementality tests: a random 15% of users held out of advertising",
        "licence": "CC BY-NC-SA 4.0 (non-commercial)",
        "source": "https://huggingface.co/datasets/criteo/criteo-uplift",
    },
    "hillstrom": {
        "what": "Retail e-mail test: 64,000 recent customers sent a men's or women's e-mail, or none, at random",
        "licence": "published by Kevin Hillstrom (MineThatData) for analysis; no licence stated",
        "source": "http://www.minethatdata.com/Kevin_Hillstrom_MineThatData_E-MailAnalytics_DataMiningChallenge_2008.03.20.csv",
    },
}


# ---------------------------------------------------------------- data
def load(name: str) -> tuple[pd.DataFrame, list[str], dict[str, np.ndarray], list[str], dict[str, bool]]:
    """Returns (features, feature names, treatment arm -> 0/1 array with NaN for other arms,
    outcome names, outcome -> is binary)."""
    path = ROOT / DATA[name]["path"]
    if not path.exists():
        raise SystemExit(f"missing {path.relative_to(ROOT)}: run `python scripts/get_data.py {name}` first")
    if name == "criteo":
        feats = [f"f{i}" for i in range(12)]
        dtypes = {**dict.fromkeys(feats, "float32"), "treatment": "int8", "conversion": "int8", "visit": "int8"}
        df = pd.read_csv(path, usecols=[*feats, "treatment", "conversion", "visit"], dtype=dtypes)
        arms = {"ads": df["treatment"].to_numpy().astype(float)}
        return df, feats, arms, ["visit", "conversion"], {"visit": True, "conversion": True}
    df = pd.read_csv(path)
    df["zip_urban"] = (df["zip_code"] == "Urban").astype(float)
    df["zip_suburban"] = (df["zip_code"] == "Surburban").astype(float)  # spelt this way in the file
    df["channel_web"] = (df["channel"] == "Web").astype(float)
    df["channel_phone"] = (df["channel"] == "Phone").astype(float)
    feats = [
        "recency",
        "history",
        "mens",
        "womens",
        "newbie",
        "zip_urban",
        "zip_suburban",
        "channel_web",
        "channel_phone",
    ]
    seg = df["segment"].to_numpy()
    arms = {
        "womens_email": np.where(seg == "Womens E-Mail", 1.0, np.where(seg == "No E-Mail", 0.0, np.nan)),
        "mens_email": np.where(seg == "Mens E-Mail", 1.0, np.where(seg == "No E-Mail", 0.0, np.nan)),
    }
    return df, feats, arms, ["visit", "conversion", "spend"], {"visit": True, "conversion": True, "spend": False}


# ---------------------------------------------------------------- models
def _params(big: bool) -> dict:
    if big:
        return {"max_iter": 300, "learning_rate": 0.08, "max_leaf_nodes": 63, "min_samples_leaf": 500}
    return {"max_iter": 200, "learning_rate": 0.05, "max_leaf_nodes": 15, "min_samples_leaf": 100}


def outcome_model(binary: bool, big: bool, seed: int):
    cls = HistGradientBoostingClassifier if binary else HistGradientBoostingRegressor
    return cls(early_stopping=True, random_state=seed, **_params(big))


def effect_model(big: bool, seed: int):
    return HistGradientBoostingRegressor(early_stopping=True, random_state=seed, **_params(big))


def predict(m, x) -> np.ndarray:
    return m.predict_proba(x)[:, 1] if hasattr(m, "predict_proba") else m.predict(x)


def rank_scores(
    xtr: np.ndarray, ttr: np.ndarray, ytr: np.ndarray, xte: np.ndarray, binary: bool, big: bool, seed: int
) -> dict[str, np.ndarray]:
    """Scores of the five rankings for the test customers (higher = target first)."""
    rng = np.random.default_rng(seed)
    tr, co = ttr == 1, ttr == 0
    mu1 = outcome_model(binary, big, seed).fit(xtr[tr], ytr[tr])
    mu0 = outcome_model(binary, big, seed + 1).fit(xtr[co], ytr[co])
    p1, p0 = predict(mu1, xte), predict(mu0, xte)
    s = outcome_model(binary, big, seed + 2).fit(np.column_stack([xtr, ttr]), ytr)
    s1 = predict(s, np.column_stack([xte, np.ones(len(xte))]))
    s0 = predict(s, np.column_stack([xte, np.zeros(len(xte))]))
    # X-learner: each group's outcomes against the other group's model, then a model of those effects
    d1 = ytr[tr] - predict(mu0, xtr[tr])
    d0 = predict(mu1, xtr[co]) - ytr[co]
    tau1 = effect_model(big, seed + 3).fit(xtr[tr], d1)
    tau0 = effect_model(big, seed + 4).fit(xtr[co], d0)
    e = float(tr.mean())  # share treated: the propensity, constant in a randomised test
    x = e * tau0.predict(xte) + (1 - e) * tau1.predict(xte)
    return {
        "random": rng.random(len(xte)),
        "response": p1,
        "s_learner": s1 - s0,
        "t_learner": p1 - p0,
        "x_learner": x,
    }


# ---------------------------------------------------------------- metrics
def binned(score: np.ndarray, t: np.ndarray, y: np.ndarray) -> dict[str, np.ndarray]:
    """Per group of the ranking (BINS equal groups, best first): customers treated and not, and
    their summed outcomes. Ties keep the (shuffled) test order."""
    order = np.argsort(-score, kind="stable")
    ts, ys = t[order].astype(float), y[order].astype(float)
    edges = np.linspace(0, len(ts), BINS + 1).astype(int)
    start = edges[:-1]
    n = np.diff(edges).astype(float)
    nt = np.add.reduceat(ts, start)
    return {
        "nt": nt,
        "nc": n - nt,
        "yt": np.add.reduceat(ys * ts, start),
        "yc": np.add.reduceat(ys * (1 - ts), start),
        "n": n,
    }


def curve_metrics(nt, nc, yt, yc, n) -> dict[str, np.ndarray]:
    """Metrics from per-group sums; every argument may carry a leading axis of resamples."""
    NT, NC, YT, YC, N = (np.cumsum(a, axis=-1) for a in (nt, nc, yt, yc, n))
    q = YT - YC * np.divide(NT, NC, out=np.zeros_like(NT), where=NC > 0)
    total = q[..., -1:]
    frac = N / N[..., -1:]
    q0 = np.concatenate([np.zeros_like(total), q], axis=-1)
    f0 = np.concatenate([np.zeros_like(total), frac], axis=-1)
    area = np.trapezoid(q0 - f0 * total, f0, axis=-1)
    k = int(round(TOP * BINS)) - 1
    with np.errstate(divide="ignore", invalid="ignore"):
        top = YT[..., k] / NT[..., k] - YC[..., k] / NC[..., k]
        avg = YT[..., -1] / NT[..., -1] - YC[..., -1] / NC[..., -1]
        return {
            "top30_share_of_total_lift": q[..., k] / total[..., 0],
            "qini_ours": area / np.abs(total[..., 0]),
            "uplift_top30_per_customer": top,
            "uplift_average_per_customer": avg,
            "top30_against_average": top / avg,
        }


def bootstrap(b: dict, binary: bool, score_sorted_parts=None, rng=None) -> dict[str, np.ndarray]:
    """BOOT Poisson-bootstrap resamples of the test set. For a 0/1 outcome each group's four cells
    (treated or not, outcome 0 or 1) are independent Poisson counts, which is exactly a row-level
    Poisson bootstrap with the ranking held fixed; for a money outcome the rows are reweighted."""
    rng = rng or np.random.default_rng(0)
    if binary:
        c = {
            "t1": b["yt"],
            "t0": b["nt"] - b["yt"],
            "c1": b["yc"],
            "c0": b["nc"] - b["yc"],
        }
        d = {k: rng.poisson(np.broadcast_to(v, (BOOT, BINS))).astype(float) for k, v in c.items()}
        nt, nc = d["t1"] + d["t0"], d["c1"] + d["c0"]
        return curve_metrics(nt, nc, d["t1"], d["c1"], nt + nc)
    ts, ys, start = score_sorted_parts
    out = {k: np.empty(BOOT) for k in curve_metrics(*(np.ones(BINS),) * 5)}
    for i in range(BOOT):
        w = rng.poisson(1.0, len(ts)).astype(float)
        nt = np.add.reduceat(w * ts, start)
        n = np.add.reduceat(w, start)
        m = curve_metrics(nt, n - nt, np.add.reduceat(w * ys * ts, start), np.add.reduceat(w * ys * (1 - ts), start), n)
        for k, v in m.items():
            out[k][i] = v
    return out


def qini_auc_library(y, score, t) -> float | None:
    """scikit-uplift's qini_auc_score (normalised by the perfect ranking), if the library is installed.
    The library accepts only 0/1 outcomes, so a money outcome has no library figure."""
    try:
        from sklift.metrics import qini_auc_score
    except ImportError:
        return None
    if not np.isin(np.unique(y), (0, 1)).all():
        return None
    return float(qini_auc_score(y, score, t))


def summary(points: list[float], boot: np.ndarray | None, ndigits: int = 4) -> dict:
    p = [float(v) for v in points if v is not None and np.isfinite(v)]
    out: dict = {"value": round(p[0], ndigits) if p else None}
    if boot is not None:
        ok = boot[np.isfinite(boot)]
        out["interval_90"] = [
            round(float(np.quantile(ok, 0.05)), ndigits),
            round(float(np.quantile(ok, 0.95)), ndigits),
        ]
    if len(p) > 1:
        out["splits"] = [round(v, ndigits) for v in p]
        out["splits_mean"] = round(float(np.mean(p)), ndigits)
        out["splits_sd"] = round(float(np.std(p, ddof=1)), ndigits)
    return out


# ---------------------------------------------------------------- run
def evaluate(name: str, train_rows: int, splits: int) -> dict:
    t0 = time.time()
    df, feats, arms, outcomes, is_binary = load(name)
    big = name == "criteo"
    out: dict = {
        "dataset": name,
        **ABOUT[name],
        "rows": int(len(df)),
        "sha256": DATA[name]["sha256"],
        "rankings": {
            "random": "random order (the floor)",
            "response": "predicted outcome if treated: finds people likely to act anyway",
            "s_learner": "one model with the treatment as an input",
            "t_learner": "one model per group (TrueLift's method)",
            "x_learner": "X-learner (Kunzel et al. 2019)",
        },
        "measures": {
            "top30_share_of_total_lift": "share of the campaign's total incremental outcome in the top 30% of the "
            "ranking",
            "uplift_top30_per_customer": "treated minus untreated outcome per customer within the top 30%",
            "top30_against_average": "that, divided by the same difference over everyone",
            "qini_ours": "area between the Qini curve and the random line, divided by the campaign's total gain "
            "(this project's own normalisation)",
            "qini_auc_score": "scikit-uplift's qini_auc_score: the same area divided by a perfect ranking's "
            "(0/1 outcomes only)",
        },
        "splits": splits,
        "bootstrap_resamples": BOOT,
        "results": [],
    }
    x_all = df[feats].to_numpy(np.float32)
    y_all = {label: df[label].to_numpy() for label in outcomes}
    del df  # Criteo: keep only the arrays (about 1 GB)
    for arm, treat in arms.items():
        keep = ~np.isnan(treat)
        x = x_all if keep.all() else x_all[keep]
        t = treat[keep].astype(np.int8)
        for label in outcomes:
            y = y_all[label][keep].astype(np.int8 if is_binary[label] else np.float32)
            per_split: dict[str, dict[str, list]] = {r: {} for r in RANKINGS}
            boot: dict[str, dict] = {}
            curve: dict[str, list] = {}
            info: dict = {}
            for sp in range(splits):
                rng = np.random.default_rng(100 + sp)
                is_train = rng.random(len(t)) < 0.7
                tr_idx = np.flatnonzero(is_train)
                if len(tr_idx) > train_rows:
                    tr_idx = rng.choice(tr_idx, train_rows, replace=False)
                te_idx = rng.permutation(np.flatnonzero(~is_train))  # shuffled: ties break at random
                scores = rank_scores(x[tr_idx], t[tr_idx], y[tr_idx], x[te_idx], is_binary[label], big, seed=sp)
                tt, yy = t[te_idx], y[te_idx].astype(float)
                if sp == 0:
                    info = {
                        "train_rows": int(len(tr_idx)),
                        "test_rows": int(len(te_idx)),
                        "share_treated": round(float(tt.mean()), 3),
                        "mean_treated": round(float(yy[tt == 1].mean()), 5),
                        "mean_untreated": round(float(yy[tt == 0].mean()), 5),
                    }
                for r, s in scores.items():
                    b = binned(s, tt, yy)
                    m = curve_metrics(b["nt"], b["nc"], b["yt"], b["yc"], b["n"])
                    for k, v in m.items():
                        per_split[r].setdefault(k, []).append(float(v))
                    per_split[r].setdefault("qini_auc_score", []).append(qini_auc_library(yy, s, tt))
                    if sp == 0:
                        parts = None
                        if not is_binary[label]:
                            order = np.argsort(-s, kind="stable")
                            start = np.linspace(0, len(tt), BINS + 1).astype(int)[:-1]
                            parts = (tt[order].astype(float), yy[order], start)
                        boot[r] = bootstrap(b, is_binary[label], parts, np.random.default_rng(7))
                        # the Qini curve at every 5% of customers, as shares of the total gain
                        NT, NC, YT, YC = (np.cumsum(b[k]) for k in ("nt", "nc", "yt", "yc"))
                        q = YT - YC * np.divide(NT, NC, out=np.zeros_like(NT), where=NC > 0)
                        idx = np.arange(BINS // 20 - 1, BINS, BINS // 20)
                        curve[r] = [0.0] + [round(float(v / q[-1]), 4) for v in q[idx]] if q[-1] else []
                print(f"{name} {arm} {label} split {sp + 1}/{splits} ({time.time() - t0:.0f}s)", flush=True)
            res = {"arm": arm, "label": label, **info, "rankings": {}}
            for r in RANKINGS:
                res["rankings"][r] = {
                    k: summary(v, boot[r].get(k) if k in boot[r] else None) for k, v in per_split[r].items()
                }
            res["curve"] = {"share_targeted": [round(i / 20, 2) for i in range(21)], **curve}
            out["results"].append(res)
    out["meta"] = meta(t0)
    return out


def meta(t0: float) -> dict:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    except OSError:
        commit = ""
    try:
        import sklift

        sk = sklift.__version__
    except ImportError:
        sk = None
    return {
        "commit": commit,
        "finished_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "wall_seconds": round(time.time() - t0),
        "python": platform.python_version(),
        "libraries": {
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit-learn": sklearn.__version__,
            "scikit-uplift": sk,
        },
        "platform": platform.platform(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Uplift rankings on real randomised experiments")
    ap.add_argument("dataset", choices=sorted(ABOUT))
    ap.add_argument("--train-rows", type=int, default=2_000_000, help="training rows per split (Criteo)")
    ap.add_argument("--splits", type=int, default=SPLITS)
    ap.add_argument("--check-data", action="store_true", help="verify the file's SHA-256 first")
    args = ap.parse_args()
    if args.check_data and sha256(ROOT / DATA[args.dataset]["path"]) != DATA[args.dataset]["sha256"]:
        raise SystemExit("the data file does not match its recorded checksum: run scripts/get_data.py again")
    out = evaluate(args.dataset, args.train_rows, args.splits)
    (ROOT / "reports").mkdir(exist_ok=True)
    dest = ROOT / f"reports/uplift_validation_{args.dataset}.json"
    dest.write_text(json.dumps(out, indent=1), encoding="utf-8")
    for r in out["results"]:
        top = {k: v["top30_share_of_total_lift"]["value"] for k, v in r["rankings"].items()}
        print(r["arm"], r["label"], "top 30% share:", top)
    print(f"wrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
