"""Uplift learner benchmark on the simulator (audit WP-39b, A05 L3, L5, L7).

    python scripts/benchmark_learners.py                  # seeds 7-11, 3 at a time -> reports/learner_benchmark.json
    python scripts/benchmark_learners.py --seeds 7 --workers 1

Every learner is trained on the same shadow-phase history (random designs, 10% random holdout) and
scored on the next week's visits to restaurants running today's blanket offer, where the simulator
knows each visit's true uplift (chance of ordering with the offer minus without it). Learners:

  random     a random score: the floor
  response   chance of ordering when shown the offer (the with-offer model alone): targets buyers,
             not persuadable customers, a common mistake
  rule       "new to this restaurant" (the simple rule the pitch compares against)
  s_learner  one model with "shown" as an input (S-learner)
  t_learner  TrueLift's model: separate with-offer and without-offer models (T-learner)
  x_learner  X-learner (Kunzel et al. 2019), with the known 90/10 assignment as propensity
  dr_learner doubly robust pseudo-outcome regression (Kennedy 2023), same propensity
  oracle     the true uplift in orders: the ceiling for ranking by orders

Metrics, on shown visits (the truth is known there): correlation with the true uplift; normalised
Qini (area between the learner's cumulative true-uplift curve and random targeting, as a share of
the oracle's); share of all true extra orders found in the top 30% of visits; restaurant profit of
targeting the top 30% as a share of the best possible (the top 30% by true profit gain; ranking by
true orders, the oracle, does not reach it). TrueLift's model also gets a reliability table
(predicted against true uplift by decile) and a check that needs no simulator: the uplift in its
top 30% and bottom 70% estimated from the random holdout alone, against the truth.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from run_pipeline import KEPT, flat_depth, log, run_meta  # noqa: E402

from truelift.economics import Terms  # noqa: E402
from truelift.model import BASE_FEATURES, design_columns  # noqa: E402
from truelift.sim import Config, Market, Policy  # noqa: E402
from truelift.training import train  # noqa: E402

LEARNERS = ("random", "response", "rule", "s_learner", "t_learner", "x_learner", "dr_learner", "oracle")
TOP = 0.30
HOLDOUT = 0.10  # the shadow phase's random holdout: the known chance of not being shown


def _params(seed: int) -> dict:
    return dict(
        max_iter=300,
        learning_rate=0.08,
        max_leaf_nodes=31,
        min_samples_leaf=200,
        l2_regularization=1.0,
        early_stopping=True,
        validation_fraction=0.1,
        random_state=seed,
    )


def _x(df: pd.DataFrame) -> pd.DataFrame:
    """Customer, restaurant and offer inputs (the same ones TrueLift's model uses)."""
    return pd.concat([df[BASE_FEATURES], design_columns(df)], axis=1)


def fit_learners(rows: pd.DataFrame, trained, seed: int):
    """Scorers for every learner, fitted on the shadow-phase rows. Each maps evaluation rows to
    predicted uplift in the chance of ordering."""
    model = trained.model
    shown = rows["shown"].to_numpy()
    y = rows["chosen"].to_numpy().astype(float)

    # S-learner: one classifier, "shown" is just another input
    xs = _x(rows).assign(shown=shown.astype(float))
    s = HistGradientBoostingClassifier(**_params(seed + 11)).fit(xs, y)

    # randomised part of the history: visits eligible for an offer, shown (90%) or held out (10%)
    rnd = rows[rows["shown"] | rows["holdout"]]
    t_r = rnd["shown"].to_numpy()
    y_r = rnd["chosen"].to_numpy().astype(float)
    x_r = _x(rnd)
    m0_r = model.p0(rnd)
    m1_r = model.p1(rnd, rnd["offer_discount"].to_numpy(), rnd["min_order"].to_numpy())
    e = 1.0 - HOLDOUT
    # X-learner: impute each group's effect with the other group's model, then combine by propensity
    tau1 = HistGradientBoostingRegressor(**_params(seed + 12)).fit(x_r[t_r], (y_r - m0_r)[t_r])
    tau0 = HistGradientBoostingRegressor(**_params(seed + 13)).fit(x_r[~t_r], (m1_r - y_r)[~t_r])
    # DR-learner: doubly robust pseudo-outcome
    psi = m1_r - m0_r + t_r * (y_r - m1_r) / e - (~t_r) * (y_r - m0_r) / (1 - e)
    dr = HistGradientBoostingRegressor(**_params(seed + 14)).fit(x_r, psi)

    def t_learner(ev):
        return model.p1(ev, ev["offer_discount"].to_numpy(), ev["min_order"].to_numpy()) - model.p0(ev)

    def s_learner(ev):
        x = _x(ev)
        return s.predict_proba(x.assign(shown=1.0))[:, 1] - s.predict_proba(x.assign(shown=0.0))[:, 1]

    rng = np.random.default_rng(seed)
    return {
        "random": lambda ev: rng.random(len(ev)),
        "response": lambda ev: model.p1(ev, ev["offer_discount"].to_numpy(), ev["min_order"].to_numpy()),
        # the rule ranks new-to-restaurant visits first; ties broken at random
        "rule": lambda ev: (ev["cr_orders_all"].to_numpy() == 0) + 0.01 * rng.random(len(ev)),
        "s_learner": s_learner,
        "t_learner": t_learner,
        "x_learner": lambda ev: e * tau0.predict(_x(ev)) + (1 - e) * tau1.predict(_x(ev)),
        "dr_learner": lambda ev: dr.predict(_x(ev)),
        "oracle": lambda ev: (ev["p"] - ev["p_cf"]).to_numpy(),
    }


def qini_area(score: np.ndarray, truth: np.ndarray) -> float:
    """Area between the cumulative true-uplift curve (visits sorted by score) and random targeting."""
    order = np.argsort(-score, kind="stable")
    cum = np.cumsum(truth[order])
    n = len(truth)
    return float((cum - np.arange(1, n + 1) / n * truth.sum()).mean())


def top_share(score: np.ndarray, value: np.ndarray, share: float = TOP) -> float:
    k = int(round(share * len(value)))
    return float(value[np.argsort(-score, kind="stable")[:k]].sum())


def holdout_check(score: np.ndarray, ev: pd.DataFrame) -> dict:
    """Uplift in the learner's top 30% and bottom 70%, estimated from the random holdout alone
    (orders per visit, shown minus held out), against the true average uplift of the same visits."""
    cut = np.quantile(score, 1 - TOP)
    out = {}
    sh, ho = ev["shown"].to_numpy(), ev["holdout"].to_numpy()
    ch = ev["chosen"].to_numpy().astype(float)
    true = (ev["p"] - ev["p_cf"]).to_numpy()
    for name, part in (("top_30pct", score >= cut), ("bottom_70pct", score < cut)):
        a, b = ch[part & sh], ch[part & ho]
        est = a.mean() - b.mean()
        se = math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
        truth = float(true[part & sh].mean())
        out[name] = {
            "estimate": round(float(est), 4),
            "low_80": round(float(est - 1.2816 * se), 4),
            "high_80": round(float(est + 1.2816 * se), 4),
            "truth": round(truth, 4),
            "truth_inside_80": bool(abs(est - truth) <= 1.2816 * se),
            "held_out_visits": int(len(b)),
        }
    return out


def reliability(score: np.ndarray, truth: np.ndarray, bins: int = 10) -> dict:
    """Mean predicted and mean true uplift by decile of the prediction, and the slope of truth on
    prediction (1 = right on average; below 1 = predictions too spread out)."""
    edges = np.quantile(score, np.linspace(0, 1, bins + 1))
    idx = np.clip(np.searchsorted(edges, score, side="right") - 1, 0, bins - 1)
    table = [
        {
            "decile": int(b + 1),
            "predicted": round(float(score[idx == b].mean()), 4),
            "true": round(float(truth[idx == b].mean()), 4),
        }
        for b in range(bins)
        if (idx == b).any()
    ]
    slope = float(np.polyfit(score, truth, 1)[0])
    return {"by_decile": table, "slope_true_on_predicted": round(slope, 3)}


def benchmark(seed: int) -> dict:
    from threadpoolctl import threadpool_limits

    with threadpool_limits(limits=2):
        R = pd.read_csv(ROOT / "data/processed/restaurants.csv")
        market = Market(R, Config(customers_per_locality=2000, seed=seed), Terms())
        trained = train(market)
        rows = trained.train
        scorers = fit_learners(rows, trained, seed)
        # next week's visits under today's blanket offer, with a random 10% holdout
        n = market.n_rest
        blanket = replace(Policy.none(n), discount=flat_depth(market.aov), holdout=HOLDOUT, name="blanket")
        occ = market.occasions(1)
        res = market.run_week(occ, blanket, market.flat_features(trained.hist, occ), salt=3, truth=True)
        m = res["eligible"]
        ev = pd.DataFrame({k: res[k][m] for k in KEPT})
        ev["offer_discount"] = blanket.discount[ev["rest"].to_numpy()]
        ev["min_order"] = 0.0
        shown = ev[ev["shown"]].reset_index(drop=True)
        tau = (shown["p"] - shown["p_cf"]).to_numpy()
        gain = (shown["p"] * shown["profit"] - shown["p_cf"] * shown["profit_cf"]).to_numpy()
        oracle_q = qini_area(tau, tau)
        oracle_top = top_share(tau, tau)
        oracle_value = top_share(gain, gain)
        out = {}
        for name in LEARNERS:
            sc = np.asarray(scorers[name](shown), float)
            out[name] = {
                "corr_with_true_uplift": round(float(np.corrcoef(sc, tau)[0, 1]), 3),
                "normalised_qini": round(qini_area(sc, tau) / oracle_q, 3),
                "share_of_extra_orders_in_top_30pct": round(top_share(sc, tau) / tau.sum(), 3),
                "top_30pct_vs_oracle": round(top_share(sc, tau) / oracle_top, 3),
                "profit_top_30pct_vs_best_possible": round(top_share(sc, gain) / oracle_value, 3),
            }
        t_all = scorers["t_learner"](ev)
        extra = {
            "reliability_t_learner": reliability(np.asarray(scorers["t_learner"](shown)), tau),
            "holdout_only_check_t_learner": holdout_check(np.asarray(t_all), ev),
            "evaluation_visits_shown": int(len(shown)),
            "training_rows": int(len(rows)),
        }
    return {"seed": seed, "learners": out, **extra}


def summary(by_seed: list[dict]) -> dict:
    out = {}
    for name in LEARNERS:
        out[name] = {}
        for metric in by_seed[0]["learners"][name]:
            v = np.array([r["learners"][name][metric] for r in by_seed], float)
            out[name][metric] = {
                "mean": round(float(v.mean()), 3),
                "sd": round(float(v.std(ddof=1)), 3) if len(v) > 1 else 0.0,
            }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seeds", default="7,8,9,10,11")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--out", type=Path, default=ROOT / "reports")
    args = ap.parse_args()
    args.quick = True
    started = time.time()
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    log(f"learner benchmark: seeds {seeds}, {args.workers} at a time")
    if args.workers <= 1:
        runs = [benchmark(s) for s in seeds]
    else:
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            runs = list(pool.map(benchmark, seeds))
    report = {
        "meta": run_meta(args, Config(customers_per_locality=2000, seed=seeds[0]), started),
        "summary": summary(runs),
        "by_seed": runs,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "learner_benchmark.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    log(f"wrote {args.out / 'learner_benchmark.json'}")
    for name, m in report["summary"].items():
        q, top = m["normalised_qini"], m["profit_top_30pct_vs_best_possible"]
        print(
            f"  {name:11s} Qini {q['mean']:.3f} ± {q['sd']:.3f}   profit of top 30% vs best possible {top['mean']:.3f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
