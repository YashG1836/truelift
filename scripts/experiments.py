"""Experiments behind the claims in the write-up that the main pipeline does not produce (audit TL-026,
A07 R4, A16 O8, A19 4.2). Each subcommand writes reports/exp_<name>.json.

    python scripts/experiments.py all                 # every experiment, full market (~15 min)
    python scripts/experiments.py oracle --quick      # one experiment on the quick market

  oracle              one fixed discount: how much of a perfect oracle's gain over blanket offers
                      the model's targeting captures
  depth-choice        profit when the model also picks the discount size (TrueLift keeps the owner's)
  variance-reduction  noise of the offer's own estimate with and without subtracting each visit's
                      predicted no-offer outcome, over ten holdout draws
  holdout-draws       error of the weekly estimate over ten holdout draws (is it centred on the truth?)
  retrain-loop        retrain on the first two evaluation weeks; promote only if better on the next two
  depth-test          customers split at random between two discount sizes (and the control group):
                      how often four weeks pick the truly better size

All outcomes are simulated; the simulator knows each visit's true effect, which is what makes these
checks possible.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from measurement_study import measure_offers  # noqa: E402
from run_pipeline import (  # noqa: E402
    EVAL_WEEKS,
    choose_designs,
    flat_depth,
    log,
    policy_from_designs,
    run_meta,
    run_world,
    summarise,
)

from truelift.economics import Terms  # noqa: E402
from truelift.engine import Z80, Design, Engine, design_options, effect_and_se  # noqa: E402
from truelift.model import UpliftModel, qini_coefficient  # noqa: E402
from truelift.sim import Config, Market, Policy, recent_visits  # noqa: E402
from truelift.training import Trained  # noqa: E402
from truelift.training import train as train_model  # noqa: E402

DRAWS = 10


@dataclass
class Ctx:
    market: Market
    trained: Trained
    engine: Engine
    by_rest: dict
    depth: np.ndarray
    designs: list
    quotes: list
    mixes: np.ndarray
    truelift: Policy
    blanket: Policy
    base: dict


def setup(quick: bool) -> Ctx:
    cfg = Config(customers_per_locality=2000) if quick else Config()
    market = Market(pd.read_csv(ROOT / "data/processed/restaurants.csv"), cfg, Terms())
    trained = train_model(market, log)
    engine, aov, n = trained.engine, market.aov, market.n_rest
    visits = recent_visits(market, trained.hist)
    by_rest = dict(tuple(visits.groupby("rest")))
    depth = flat_depth(aov)
    designs, quotes = choose_designs(engine, by_rest, depth, aov, trained.baskets)
    mixes = np.array([engine.mix(trained.baskets[r], designs[r], aov[r]) for r in range(n)])
    blanket = replace(Policy.none(n), discount=depth.copy(), name="today: blanket")
    base = run_world(market, trained.hist, Policy.none(n))
    tl = policy_from_designs(designs, engine, mixes, "TrueLift")
    return Ctx(market, trained, engine, by_rest, depth, designs, quotes, mixes, tl, blanket, base)


def _round(x: float, k: int = 0):
    return round(float(x), k) if k else round(float(x))


# ---------------------------------------------------------------- oracle
def oracle(c: Ctx) -> dict:
    """Blanket offer at every restaurant, everyone shown: each visit's true own gain is known.
    Model targeting keeps the visits with predicted gain > 0; the oracle keeps those with true gain
    > 0. Interactions between restaurants' targeting are left out (each visit's gain is its own)."""
    w = run_world(c.market, c.trained.hist, replace(c.blanket, holdout=0.0), keep_rows=True)
    rows = w["rows"]
    rr = rows["rest"].to_numpy()
    g = (rows["p"] * rows["profit"] - rows["p_cf"] * rows["profit_cf"]).to_numpy()
    mx = np.array(
        [c.engine.mix(c.trained.baskets[r], Design(float(c.depth[r])), c.market.aov[r]) for r in range(len(c.depth))]
    )
    v = c.engine.row_values(rows, c.depth[rr], 0.0, 0.0, 0.0, tuple(mx[rr, i] for i in range(4)))
    pred = v["gain"]
    weeks = len(EVAL_WEEKS)
    blanket, model, best = g.sum() / weeks, g[pred > 0].sum() / weeks, g[g > 0].sum() / weeks
    random_same_share = (pred > 0).mean() * blanket
    return {
        "blanket_profit_gain_a_week": _round(blanket),
        "model_targeting_profit_gain_a_week": _round(model),
        "oracle_profit_gain_a_week": _round(best),
        "random_targeting_same_share_a_week": _round(random_same_share),
        "share_of_visits_targeted_by_model": _round((pred > 0).mean(), 3),
        "share_of_oracle_gain_over_blanket_captured": _round((model - blanket) / (best - blanket), 3)
        if best > blanket
        else None,
        "note": "one fixed discount (15% of the average order) at every restaurant; per-visit own gains",
    }


# ---------------------------------------------------------------- depth choice
def depth_choice(c: Ctx) -> dict:
    """Let the model also pick the size among the create screen's depths, against TrueLift as it
    is (owner's size kept). Both evaluated on the same weeks; own-offer and market-wide profit."""
    n, aov = c.market.n_rest, c.market.aov
    chosen, changed = [], 0
    for r in range(n):
        x = c.by_rest.get(r)
        if x is None:
            chosen.append(Design(0.0))
            continue
        x = x.drop(columns=["rest", "cust", "week"])
        best = None
        for dp in design_options(aov[r])["depths"]:
            _, b = c.engine.best_design(x, Design(float(dp)), aov[r], c.trained.baskets[r], weeks=2)
            if best is None or b["profit_change"] > best["profit_change"]:
                best = b
        d = Design(**best["design"]) if best and best["profit_change"] > 0 else Design(0.0)
        changed += int(d.discount > 0 and d.discount != c.depth[r])
        chosen.append(d)
    mx = np.array([c.engine.mix(c.trained.baskets[r], chosen[r], aov[r]) for r in range(n)])
    free = summarise(
        run_world(c.market, c.trained.hist, policy_from_designs(chosen, c.engine, mx, "free size")), c.base
    )
    kept = summarise(run_world(c.market, c.trained.hist, c.truelift), c.base)
    keys = ("own_offer_profit_effect", "restaurant_profit_change", "offers_that_pay", "offers_that_lose")
    return {
        "owner_size_kept": {k: kept[k] for k in keys},
        "model_picks_size": {k: free[k] for k in keys},
        "restaurants_where_model_changed_size": changed,
    }


# ---------------------------------------------------------------- holdout draws (two experiments)
def _draws(c: Ctx, draws: int = DRAWS) -> list[pd.DataFrame]:
    out = []
    for k in range(draws):
        w = run_world(c.market, c.trained.hist, c.truelift, keep_rows=True, salt=100 + k)
        out.append(w["rows"])
        log(f"holdout draw {k + 1}/{draws}")
    return out


def variance_reduction(c: Ctx, all_rows: list[pd.DataFrame]) -> dict:
    """The offer's own estimate (shown minus held out, profit, four weeks) with and without
    subtracting each visit's predicted no-offer profit, across holdout draws: root mean square error
    against the truth, pooled over offers."""
    err_raw, err_adj = [], []
    for rows in all_rows:
        for r, g in rows.groupby("rest"):
            d = c.designs[int(r)]
            if d.discount <= 0:
                continue
            sh, ho = g["shown"].to_numpy(), g["holdout"].to_numpy()
            if sh.sum() < 10 or ho.sum() < 2:
                continue
            mx = tuple(np.full(len(g), c.mixes[int(r), i]) for i in range(4))
            v = c.engine.row_values(g, d.discount, d.min_order, d.reward, d.zomato_share, mx)
            y = (g["chosen"] * g["profit"]).to_numpy(float)
            truth = float((g["p"] * g["profit"] - g["p_cf"] * g["profit_cf"]).to_numpy()[sh].sum())
            cust = g["cust"].to_numpy()
            raw, _ = effect_and_se(y, sh, ho, cust, min_events=0)
            adj, _ = effect_and_se(y, sh, ho, cust, base=v["p0"] * v["profit0"], min_events=0)
            err_raw.append(raw * sh.sum() - truth)
            err_adj.append(adj * sh.sum() - truth)
    rms_raw = math.sqrt(float(np.mean(np.square(err_raw))))
    rms_adj = math.sqrt(float(np.mean(np.square(err_adj))))
    return {
        "draws": len(all_rows),
        "offer_draws": len(err_raw),
        "rmse_without_adjustment": _round(rms_raw),
        "rmse_with_adjustment": _round(rms_adj),
        "noise_cut": _round(1 - rms_adj / rms_raw, 3),
        "note": "offer's own control group only (no model prior), profit over four weeks, Rs",
    }


def holdout_draws(c: Ctx, all_rows: list[pd.DataFrame]) -> dict:
    """The full weekly estimate (own control group + calibrated prior) after four weeks, per offer,
    across holdout draws: mean error (should be near zero), and how often the 80% range holds the truth."""
    per = []
    weekly_el = {r: q[1]["eligible_visits"] for r, q in enumerate(c.quotes) if q[1] is not None}
    for k, rows in enumerate(all_rows):
        m = measure_offers(c.engine, rows, c.designs, c.market.aov, c.trained.baskets, (4,), weekly_el)
        m["draw"] = k
        per.append(m)
    recs = pd.concat(per, ignore_index=True)
    err = recs["est_profit"] - recs["true_profit"]
    by_offer = err.groupby(recs["rest"]).mean()
    se = float(err.std(ddof=1) / math.sqrt(len(err)))
    inside = ((recs["true_profit"] >= recs["low"]) & (recs["true_profit"] <= recs["high"])).mean()
    return {
        "draws": len(all_rows),
        "offers": int(recs["rest"].nunique()),
        "mean_error_rs": _round(err.mean()),
        "mean_error_se_rs": _round(se),
        "mean_error_within_2_se": bool(abs(err.mean()) <= 2 * se),
        "mean_abs_error_rs": _round(err.abs().mean()),
        "coverage_80": _round(inside, 3),
        "offers_with_mean_error_above_their_spread": int(
            (by_offer.abs() > 2 * err.groupby(recs["rest"]).std(ddof=1) / math.sqrt(len(all_rows))).sum()
        ),
    }


# ---------------------------------------------------------------- retrain loop
def retrain_loop(c: Ctx) -> dict:
    """The learning loop (A16 O8): after two weeks of running offers, retrain on the shadow history
    plus those weeks' shown and held-out visits, and promote the candidate only if it ranks the next
    two weeks' visits better (on the random holdout, Qini; against the truth, correlation)."""
    w = run_world(c.market, c.trained.hist, c.truelift, keep_rows=True)
    rows = w["rows"].copy()
    rr = rows["rest"].to_numpy()
    rows["offer_discount"] = c.truelift.discount[rr]
    rows["min_order"] = c.truelift.min_order[rr]
    early, late = rows[rows["week"] <= 2], rows[rows["week"] > 2]
    train = c.trained.train
    cols = [col for col in train.columns if col in early.columns]
    candidate = UpliftModel.fit(pd.concat([train[cols], early[cols]], ignore_index=True), seed=7)

    def score(model: UpliftModel) -> dict:
        up = model.p1(late, late["offer_discount"].to_numpy(), late["min_order"].to_numpy()) - model.p0(late)
        sh = late["shown"].to_numpy()
        truth = (late["p"] - late["p_cf"]).to_numpy()
        return {
            "qini_on_holdout": _round(qini_coefficient(up, sh, late["chosen"].to_numpy()), 3),
            "corr_with_true_uplift": _round(np.corrcoef(up[sh], truth[sh])[0, 1], 3),
        }

    cur, new = score(c.trained.model), score(candidate)
    return {
        "current_model": cur,
        "candidate_model": new,
        "added_training_rows": int(len(early)),
        "promote": new["qini_on_holdout"] > cur["qini_on_holdout"],
        "rule": "promote when the candidate's Qini on the next two weeks' random holdout is higher",
    }


# ---------------------------------------------------------------- depth test
def depth_test(c: Ctx) -> dict:
    """Customers shown the offer are split at random between the owner's size and the next size up
    (the control group stays). After four weeks, compare each arm with the control group, pick the
    size with the higher measured profit per visit, and check it against the truth."""
    aov = c.market.aov
    pol = replace(c.truelift)
    deeper = np.zeros(len(aov))
    for r, d in enumerate(c.designs):
        if d.discount > 0:
            opts = [x for x in design_options(aov[r])["depths"] if x > d.discount]
            deeper[r] = float(opts[0]) if opts else 0.0
    pol.depth_b = deeper
    w = run_world(c.market, c.trained.hist, pol, keep_rows=True)
    rows = w["rows"]
    recs = []
    for r, g in rows.groupby("rest"):
        if deeper[int(r)] <= 0:
            continue
        ho = g["holdout"].to_numpy()
        y = (g["chosen"] * g["profit"]).to_numpy(float)
        cust = g["cust"].to_numpy()
        gain = (g["p"] * g["profit"] - g["p_cf"] * g["profit_cf"]).to_numpy()
        arms = {}
        for name, arm in (
            ("owner_size", g["shown"].to_numpy() & ~g["arm_b"].to_numpy()),
            ("deeper", g["arm_b"].to_numpy()),
        ):
            if arm.sum() < 10 or ho.sum() < 2:
                break
            est, se = effect_and_se(y, arm, ho, cust, min_events=0)
            arms[name] = {"est": est, "se": se, "truth": float(gain[arm].mean())}
        if len(arms) < 2:
            continue
        a, b = arms["owner_size"], arms["deeper"]
        diff_se = math.sqrt(a["se"] ** 2 + b["se"] ** 2) if math.isfinite(a["se"] + b["se"]) else math.inf
        recs.append(
            {
                "rest": int(r),
                "picked_deeper": b["est"] > a["est"],
                "truly_deeper_better": b["truth"] > a["truth"],
                "confident": abs(b["est"] - a["est"]) > Z80 * diff_se,
                "visits": int(len(g)),
            }
        )
    df = pd.DataFrame(recs)
    right = df["picked_deeper"] == df["truly_deeper_better"]
    conf = df[df["confident"]]
    big = df["visits"] >= df["visits"].median()
    return {
        "offers_tested": int(len(df)),
        "share_picking_the_truly_better_size": _round(right.mean(), 3),
        "share_confident_at_80": _round(df["confident"].mean(), 3),
        "share_right_when_confident": _round((conf["picked_deeper"] == conf["truly_deeper_better"]).mean(), 3)
        if len(conf)
        else None,
        "share_right_larger_half": _round(right[big].mean(), 3),
        "share_right_smaller_half": _round(right[~big].mean(), 3),
        "share_where_deeper_truly_better": _round(df["truly_deeper_better"].mean(), 3),
        "note": "arms: the owner's size and the next size the create screen offers; 4 weeks; restaurant's "
        "own control group only",
    }


EXPERIMENTS = ("oracle", "depth-choice", "variance-reduction", "holdout-draws", "retrain-loop", "depth-test")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("name", choices=(*EXPERIMENTS, "all"))
    ap.add_argument("--quick", action="store_true", help="the quick market (2,000 customers per locality)")
    ap.add_argument("--out", type=Path, default=ROOT / "reports")
    args = ap.parse_args()
    args.seeds = ""
    started = time.time()
    names = EXPERIMENTS if args.name == "all" else (args.name,)
    c = setup(args.quick)
    draws = _draws(c) if {"variance-reduction", "holdout-draws"} & set(names) else None
    args.out.mkdir(parents=True, exist_ok=True)
    for name in names:
        t = time.time()
        if name == "variance-reduction":
            res = variance_reduction(c, draws or [])
        elif name == "holdout-draws":
            res = holdout_draws(c, draws or [])
        else:
            res = {
                "oracle": oracle,
                "depth-choice": depth_choice,
                "retrain-loop": retrain_loop,
                "depth-test": depth_test,
            }[name](c)
        report = {"meta": run_meta(args, c.market.cfg, started), "experiment": name, "result": res}
        path = args.out / f"exp_{name.replace('-', '_')}.json"
        path.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
        log(f"{name}: {time.time() - t:.0f}s -> {path.name}")
        print(json.dumps(res, indent=1, default=str)[:1500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
