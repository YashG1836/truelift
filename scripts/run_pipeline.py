"""End-to-end pipeline: simulate history, train, calibrate, compare policies, check measurement.

    .venv/bin/python scripts/run_pipeline.py            # full run, writes model + reports
    .venv/bin/python scripts/run_pipeline.py --quick    # fewer customers, for a fast check

Steps
 1. History: 8 weeks of today's market + 4 weeks of TrueLift's shadow phase (random designs, 10%
    random holdout). This is the only data the models see.
 2. Train the uplift model; calibrate its error with cross-fitting (each restaurant's error is
    measured by a model that never saw that restaurant).
 3. Evaluate 4 weeks under each policy, all restaurants at once, identical customer visits:
    no offer | today (blanket ~15% off for everyone) | rule (new customers only) |
    TrueLift (same discount size as today, TrueLift picks who sees it and the minimum order) |
    TrueLift with Zomato paying half the discount for customers new to Zomato (unmeasured).
    The simulator knows the truth, so every number below is the true expected value.
 4. Measurement check: TrueLift's weekly estimates vs the truth (error and 80% range coverage).
 5. Market analyses: Zomato-weight frontier, owners declining OTP approval, Zomato's ledger,
    partial adoption, history that moves, fairness by segment, control-set option.
 6. Scenarios (full run, in parallel): customers 30% less and 30% more price-sensitive,
    commission on the price before the discount, and four more market seeds for the spread.
Outputs: data/processed/model.pkl (+ .sha256), reports/evaluation.json, restaurants_results.csv,
measurement_check.csv, skew_check.json. The eight-assumption sweep is scripts/sensitivity.py.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from measurement_study import aa_summary, adaptive_holdout, coverage, detection, measure_offers  # noqa: E402

from truelift.assignment import stable_uniform  # noqa: E402
from truelift.economics import Terms  # noqa: E402
from truelift.engine import Design, Engine, design_options  # noqa: E402
from truelift.features import FEATURE_NAMES, skew_report  # noqa: E402
from truelift.model import UpliftModel, file_sha256, library_versions, qini_coefficient, save_bundle  # noqa: E402
from truelift.sim import (  # noqa: E402
    TYPES,
    Config,
    History,
    Market,
    Policy,
    display_name,
    recent_visits,
    status_quo_policy,
)
from truelift.training import train as train_model  # noqa: E402

EVAL_WEEKS = (1, 2, 3, 4)
AA_WEEKS = tuple(range(1, 13))  # the A/A test looks 12 times: three consent periods
MEASUREMENT_VARIANTS = (("model", "fixed"), ("model", "lin"), ("customer", "fixed"), ("visit", "fixed"))


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def code_version() -> str:
    """Date and git commit of the code that produced a result (\"nogit\" outside a checkout)."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        sha = "nogit"
    return f"{time.strftime('%Y-%m-%d')}+{sha}"


def run_meta(args: argparse.Namespace, cfg: Config, started: float, terms: Terms = Terms()) -> dict:
    """Where a report came from: code, environment, inputs, settings, time (audit A07 R3)."""
    try:
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip()
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = "nogit", ""
    return {
        "commit": commit,
        "uncommitted_changes": bool(dirty),
        "command": " ".join(["python", f"scripts/{Path(sys.argv[0]).name}", *sys.argv[1:]]),
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "wall_seconds": round(time.time() - started),
        "python": platform.python_version(),
        "libraries": library_versions(),
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "seed": cfg.seed,
        "quick": bool(args.quick),
        "config": asdict(cfg),
        "terms": asdict(terms),
        "restaurants_csv_sha256": file_sha256(ROOT / "data/processed/restaurants.csv"),
    }


KEPT = (
    *FEATURE_NAMES,
    "c_new_account",
    "c_offer_share_4w",
    "week",
    "cust",
    "rest",
    "local",
    "slot",
    "type",
    "regular",
    "eligible",
    "holdout",
    "shown",
    "share",
    "takes",
    "chosen",
    "discount",
    "reward",
    "saving",
    "basket",
    "profit",
    "p",
    "p_cf",
    "profit_cf",
)


def run_world(
    market: Market,
    hist,
    policy: Policy,
    keep_rows: bool = False,
    weeks=EVAL_WEEKS,
    holdout_by_week=None,
    segments: bool = False,
    moving: bool = False,
) -> dict:
    """Evaluation weeks under one policy. Returns true expected totals (and eligible rows if asked).

    holdout_by_week: {week: holdout share per restaurant} for weeks that differ from the policy's.
    segments: also sum visits, offers shown, discount received and orders by customer segment.
    moving: features follow the history as the weeks pass (each week is added to it), instead of
    staying at the snapshot taken when the period starts (A06 S6).
    """
    per_rest, swiggy, kept, segs = [], [], [], []
    now = History(*(list(getattr(hist, f)) for f in History.__dataclass_fields__)) if moving else hist
    for w in weeks:
        occ = market.occasions(w)
        pol = replace(policy, holdout=holdout_by_week[w]) if holdout_by_week and w in holdout_by_week else policy
        res = market.run_week(occ, pol, market.flat_features(now, occ), salt=3, truth=True)
        if moving:
            market.record(now, res)
        if segments:
            segs.append(segment_sums(market, res))
        p, sh = res["p"], res["shown"]
        df = pd.DataFrame(
            {
                "rest": res["rest"],
                "orders": p,
                "profit": p * res["profit"],
                "commission": p * res["commission"],
                "contribution": p * res["zomato_contribution"],
                "zfund": p * res["zomato_funded"],
                "spend": p * (res["discount"] + res["reward"]),
                "sales": p * res["basket"],
                "redemptions": p * res["takes"],
                "lift": np.where(sh, p - res["p_cf"], 0.0),
                "lift_profit": np.where(sh, p * res["profit"] - res["p_cf"] * res["profit_cf"], 0.0),
                # the part of the own-offer effect that comes from customers new to Zomato
                "lift_profit_new": np.where(
                    sh & (res["c_new_account"] == 1), p * res["profit"] - res["p_cf"] * res["profit_cf"], 0.0
                ),
                "platform_lift": np.where(sh, res["platform_lift"], 0.0),
            }
        )
        per_rest.append(df.groupby("rest").sum())
        first = np.r_[True, res["occ"][1:] != res["occ"][:-1]]
        swiggy.append(pd.DataFrame({"type": res["type"][first], "p_swiggy": res["p_swiggy"][first]}))
        if keep_rows:
            m = res["eligible"]
            kept.append(pd.DataFrame({k: res[k][m] for k in KEPT}))
    pr = sum(per_rest) / len(weeks)  # weekly averages per restaurant
    sw = pd.concat(swiggy)
    out = {
        "per_rest": pr.reindex(range(market.n_rest), fill_value=0.0),
        "swiggy_share": float(sw["p_swiggy"].mean()),
        "swiggy_share_loyal": float(sw.loc[sw["type"] == 0, "p_swiggy"].mean()),
    }
    if keep_rows:
        out["rows"] = pd.concat(kept, ignore_index=True)
    if segments:
        out["segments"] = pd.concat(segs).groupby(level=[0, 1]).sum() / len(weeks)
    return out


SEGMENTS = ("customer_type", "locality", "price_band", "regular", "new_account")


def segment_sums(market: Market, res: dict) -> pd.DataFrame:
    """Weekly sums by customer segment: menu visits, visits offered a saving (a discount shown or a
    Brand Pack reward), saving received (discount plus reward on the expected orders), orders."""
    p = res["p"]
    values = {
        "customer_type": np.array(TYPES, dtype=object)[res["type"]],
        "locality": np.array(market.localities, dtype=object)[market.c_loc[res["cust"]]],
        "price_band": np.array(["under Rs 300", "Rs 300-499", "Rs 500+"], dtype=object)[
            np.digitize(market.aov[res["rest"]], [300, 500])
        ],
        "regular": np.where(res["regular"], "regular here", "not a regular"),
        "new_account": np.where(res["c_new_account"] == 1, "new to Zomato", "existing"),
    }
    parts = []
    for dim in SEGMENTS:
        df = pd.DataFrame(
            {
                "dim": dim,
                "value": values[dim],
                "visits": 1.0,
                "offered": (res["shown"] | (res["reward"] > 0)).astype(float),
                "saving_received": p * (res["discount"] + res["reward"]),
                "orders": p,
            }
        )
        parts.append(df.groupby(["dim", "value"]).sum())
    return pd.concat(parts)


def summarise(world: dict, base: dict) -> dict:
    t, b = world["per_rest"].sum(), base["per_rest"].sum()
    extra = t["orders"] - b["orders"]
    d_rest = world["per_rest"]["profit"] - base["per_rest"]["profit"]
    active = world["per_rest"]["redemptions"] > 0
    return {
        "orders_per_week": round(t["orders"]),
        "extra_orders_vs_no_offer": round(extra),
        "restaurant_profit": round(t["profit"]),
        "restaurant_profit_change": round(t["profit"] - b["profit"]),
        "zomato_commission": round(t["commission"]),
        "zomato_commission_change": round(t["commission"] - b["commission"]),
        "zomato_contribution_change": round(t["contribution"] - b["contribution"]),
        "zomato_funded_discount": round(t["zfund"]),
        "customer_savings": round(t["spend"]),
        "savings_per_extra_order": round(t["spend"] / extra) if extra > 1 else None,
        "redemptions": round(t["redemptions"]),
        "anyway_share_of_redemptions": round(1 - t["lift"] / t["redemptions"], 3) if t["redemptions"] > 0 else None,
        "order_value": round(t["sales"] / t["orders"]),
        "restaurants_with_offer": int(active.sum()),
        # effect of each restaurant's own offer (others unchanged): what the owner cares about
        "own_offer_profit_effect": round(world["per_rest"]["lift_profit"].sum()),
        "own_offer_extra_orders": round(world["per_rest"]["lift"].sum()),
        "offers_that_pay": int(((world["per_rest"]["lift_profit"] > 0) & active).sum()),
        "offers_that_lose": int(((world["per_rest"]["lift_profit"] <= 0) & active).sum()),
        "platform_extra_orders": round(world["per_rest"]["platform_lift"].sum()),
        # market-wide comparison with a world where nobody runs offers
        "restaurants_better_off_vs_no_offers": int((d_rest > 1).sum()),
        "restaurants_worse_off_vs_no_offers": int((d_rest < -1).sum()),
        "swiggy_share_of_occasions": round(world["swiggy_share"], 4),
        "swiggy_share_loyal": round(world["swiggy_share_loyal"], 4),
    }


ADOPTION_GROUPS = 10  # one tenth of restaurants switch at a time


def own_effect_in_todays_market(market: Market, hist, offers: Policy) -> tuple[pd.DataFrame, list]:
    """Each restaurant's true own-offer effect when it alone (with a tenth of the market) switches
    to `offers` while everyone else keeps today's offers: the condition a quote describes.

    Returns the per-restaurant weekly truths and the ten worlds (each one is also a 10% adoption).
    """
    background = todays_market(market)
    parts, worlds = [], []
    for g in range(ADOPTION_GROUPS):
        mine = np.arange(market.n_rest) % ADOPTION_GROUPS == g
        w = run_world(market, hist, adopt(background, offers, mine, f"{offers.name}: group {g}"))
        worlds.append(w)
        parts.append(w["per_rest"][mine])
    return pd.concat(parts).sort_index(), worlds


def todays_market(market: Market) -> Policy:
    """A share of restaurants with blanket flat discounts, no holdout: the market an adopter joins."""
    return status_quo_policy(market, np.random.default_rng(4242), name="today's market")


def adopt(background: Policy, offers: Policy, mine: np.ndarray, name: str) -> Policy:
    """`background` everywhere except the restaurants in `mine`, which run `offers` (with its holdout)."""
    pol = replace(background, name=name, scorer=offers.scorer)
    for attr in ("discount", "min_order", "offpeak_only", "zomato_share", "reward", "audience"):
        arr = getattr(pol, attr).copy()
        arr[mine] = getattr(offers, attr)[mine]
        setattr(pol, attr, arr)
    pol.holdout = np.where(mine, offers.holdout, background.holdout)
    return pol


def forecast_check(qs: list, per_rest: pd.DataFrame) -> dict:
    """Quotes (one per restaurant, None if no offer) against the true weekly own-offer profit effect."""
    rows = [
        (
            q["profit_change"],
            q["profit_low"],
            q["profit_high"],
            float(per_rest["lift_profit"].iloc[r]),
            float(per_rest["lift_profit_new"].iloc[r]),
        )
        for r, q in enumerate(qs)
        if q is not None
    ]
    if not rows:
        return {"offers": 0}
    f, lo, hi, t, t_new = (np.array(c, float) for c in zip(*rows, strict=True))
    t_old = t - t_new
    return {
        "offers": len(rows),
        "forecast_total": round(float(f.sum())),
        "truth_total": round(float(t.sum())),
        "ratio_forecast_to_truth": round(float(f.sum() / t.sum()), 3) if t.sum() else None,
        "mean_abs_error": round(float(np.abs(f - t).mean())),
        "coverage_80": round(float(((t >= lo) & (t <= hi)).mean()), 3),
        "misses_below_range": int((t < lo).sum()),
        "misses_above_range": int((t > hi).sum()),
        "sign_right": round(float((np.sign(f) == np.sign(t)).mean()), 3),
        "share_forecast_below_truth": round(float((f < t).mean()), 3),
        # customers who join Zomato after the quote cannot be in a quote built from past visits
        "truth_from_new_accounts": round(float(t_new.sum())),
        "ratio_to_truth_existing_customers": round(float(f.sum() / t_old.sum()), 3) if t_old.sum() else None,
        "coverage_80_existing_customers": round(float(((t_old >= lo) & (t_old <= hi)).mean()), 3),
    }


def _point(p: dict) -> dict:
    keys = (
        "restaurant_profit_change",
        "own_offer_profit_effect",
        "zomato_commission_change",
        "zomato_contribution_change",
        "orders_per_week",
        "offers_that_pay",
        "offers_that_lose",
    )
    return {k: p[k] for k in keys if k in p}


def _first_at_or_below(xs: list, ys: list, target: float) -> float | None:
    """Smallest x at which the piecewise-linear y(x) is at or below `target` (xs ascending):
    xs[0] if it starts there, None if it never gets there."""
    if ys[0] <= target:
        return xs[0]
    for x0, y0, x1, y1 in zip(xs, ys, xs[1:], ys[1:], strict=False):
        if y1 <= target:
            return round(x0 + (y0 - target) * (x1 - x0) / (y0 - y1), 3)
    return None


def fairness_report(segs: dict) -> dict:
    """Who gets the savings, by segment, under each policy (A13 F1): share of menu visits offered a
    saving (discount shown or Brand Pack reward), saving received per visit (Rs, discount plus
    reward on expected orders) and orders per 100 visits.

    Loyalty gap: how much more often a customer who is not a regular is offered a saving than a
    regular of the same restaurant (points of share; positive = regulars are offered less)."""
    out: dict = {}
    for name, sg in segs.items():
        rows: dict = {}
        for (dim, value), r in sg.iterrows():
            rows.setdefault(dim, {})[str(value)] = {
                "share_of_visits_offered_a_saving": round(float(r["offered"] / r["visits"]), 3),
                "saving_received_per_visit": round(float(r["saving_received"] / r["visits"]), 2),
                "orders_per_100_visits": round(float(100 * r["orders"] / r["visits"]), 2),
            }
        reg = rows.get("regular", {})
        gap = None
        if "regular here" in reg and "not a regular" in reg:
            gap = round(
                reg["not a regular"]["share_of_visits_offered_a_saving"]
                - reg["regular here"]["share_of_visits_offered_a_saving"],
                3,
            )
        out[name] = {"by_segment": rows, "loyalty_gap": gap}
    return out


def widened(policy: Policy, extra) -> Policy:
    """`policy` with each offer also shown to the visits `extra(feats, mask)` picks (fairness
    mitigations). The simulator asks the scorer only for "targeted" offers, so every offer becomes
    "targeted" with a scorer that first applies the audience TrueLift chose, then widens it."""
    audience, scorer = policy.audience.copy(), policy.scorer

    def score(feats: dict, pol: Policy, mask: np.ndarray) -> np.ndarray:
        f = {k: np.asarray(feats[k])[mask] for k in ("rest", "cr_orders_all", "cr_weeks_since")}
        a = audience[f["rest"].astype(int)]
        keep = np.ones(int(mask.sum()), bool)
        new = a == "new_to_restaurant"
        keep[new] = (f["cr_orders_all"] == 0)[new]
        lapsed = a == "lapsed"
        keep[lapsed] = ((f["cr_orders_all"] > 0) & (f["cr_weeks_since"] >= 4))[lapsed]
        tg = a == "targeted"
        if tg.any() and scorer is not None:
            sub = np.zeros_like(mask)
            sub[np.flatnonzero(mask)[tg]] = True
            keep[tg] = scorer(feats, pol, sub)
        return keep | extra(feats, mask)

    targeted = np.where(policy.discount > 0, "targeted", policy.audience).astype(object)
    return replace(policy, audience=targeted, scorer=score)


def choose_designs(
    engine: Engine,
    by_rest: dict,
    depth: np.ndarray,
    aov: np.ndarray,
    baskets: list,
    zomato_share: float = 0.0,
    zomato_weight: float = 0.0,
) -> tuple[list[Design], list[tuple]]:
    """TrueLift's version for every restaurant, starting from the owner's blanket offer of `depth`.

    Returns the chosen designs (no offer where the best expected profit change is not positive) and,
    per restaurant, (quote of the owner's offer, quote of the chosen version or None)."""
    chosen, qs = [], []
    for r in range(len(depth)):
        x = by_rest.get(r)
        if x is None:
            chosen.append(Design(0.0))
            qs.append((None, None))
            continue
        owner_q, best = engine.best_design(
            x.drop(columns=["rest", "cust", "week"]),
            Design(float(depth[r]), zomato_share=zomato_share),
            aov[r],
            baskets[r],
            weeks=2,
            zomato_weight=zomato_weight,
        )
        d = Design(**best["design"]) if best["profit_change"] > 0 else Design(0.0)
        chosen.append(d)
        qs.append((owner_q, best if d.discount > 0 or d.reward > 0 else None))
    return chosen, qs


def flat_depth(aov: np.ndarray, share: float = 0.15) -> np.ndarray:
    return np.maximum(20.0, np.round(aov * share / 10) * 10)


def policy_from_designs(designs: list[Design], engine: Engine, mixes: np.ndarray, name: str) -> Policy:
    pol = Policy(
        np.array([d.discount for d in designs]),
        np.array([d.min_order for d in designs]),
        np.array([d.offpeak_only for d in designs]),
        np.array([d.zomato_share for d in designs]),
        np.array([d.reward for d in designs]),
        np.array([d.audience for d in designs], dtype=object),
        engine.holdout,
        engine.targeting_scorer(mixes),
        name,
    )
    pol.discount[pol.discount <= 0] = 0.0
    return pol


def evaluate(
    cfg: Config,
    quick: bool,
    with_details: bool,
    out_dir: Path = ROOT / "reports",
    model_out: Path = ROOT / "data/processed/model.pkl",
    terms: Terms = Terms(),
    holdout: float = 0.10,
) -> dict:
    """Simulate, train and evaluate one market. `terms` are the commercial terms (commission base
    and rate, food cost); `holdout` is the share of eligible customers TrueLift holds out."""
    t0 = time.time()
    R = pd.read_csv(ROOT / "data/processed/restaurants.csv")
    market = Market(R, cfg, terms)
    n = market.n_rest
    aov = market.aov
    trained = train_model(market, log)
    hist, baskets, engine, offers = trained.hist, trained.baskets, trained.engine, trained.offers
    engine.holdout = holdout

    # policies
    zero = Policy.none(n)
    depth = flat_depth(aov)
    blanket = Policy(
        depth.copy(),
        np.zeros(n),
        np.zeros(n, bool),
        np.zeros(n),
        np.zeros(n),
        np.array(["all"] * n, dtype=object),
        0.0,
        None,
        "today: blanket",
    )
    results: dict = {}
    rule = replace(blanket, audience=np.array(["new_to_restaurant"] * n, dtype=object), name="rule: new customers")
    visits = recent_visits(market, hist)
    by_rest = dict(tuple(visits.groupby("rest")))

    # training-serving skew: the quote's input and the evaluation weeks against the training rows
    evaluation_feats = pd.DataFrame(market.flat_features(hist, market.occasions(EVAL_WEEKS[0])))
    skew = skew_report(trained.train, {"quote_input": visits, "evaluation": evaluation_feats})
    if with_details:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "skew_check.json").write_text(json.dumps(skew, indent=1), encoding="utf-8")
    results["skew_check"] = {
        "passed": skew["passed"],
        "worst_share_outside_training": round(skew["worst_share"], 5),
        "limit": skew["limit"],
    }
    if not skew["passed"]:
        raise SystemExit(f"training-serving skew above {skew['limit']:.1%}: see skew_check.json")
    designs = {}
    quotes: dict[str, list] = {}
    for key, zshare in (("truelift", 0.0), ("truelift_cofund", 0.5)):
        designs[key], quotes[key] = choose_designs(engine, by_rest, depth, aov, baskets, zomato_share=zshare)
        log(f"{key}: designs chosen for {n} restaurants")
    mixes = {k: np.array([engine.mix(baskets[r], designs[k][r], aov[r]) for r in range(n)]) for k in designs}
    pols = {
        "no_offer": zero,
        "today_blanket": blanket,
        "rule_new_customers": rule,
        "truelift": policy_from_designs(designs["truelift"], engine, mixes["truelift"], "TrueLift"),
        "zomato_cofund_naive": policy_from_designs(
            designs["truelift_cofund"],
            engine,
            mixes["truelift_cofund"],
            "TrueLift + Zomato pays 50% for new-to-Zomato customers, unmeasured",
        ),
    }
    worlds = {}
    for k, pol in pols.items():
        worlds[k] = run_world(
            market,
            hist,
            pol,
            keep_rows=(with_details and k == "truelift"),
            segments=(with_details and k in ("today_blanket", "truelift")),
        )
    base = worlds["no_offer"]
    results["policies"] = {k: {"name": pols[k].name, **summarise(w, base)} for k, w in worlds.items()}
    log("policies evaluated")

    # forecast check (audit TL-006): the quote an owner sees before approving, against the truth
    # "in today's market": a tenth of restaurants switch at a time, as the quote assumes; "after
    # everyone switches": the whole market changes offers at once (the policy comparison's world)
    truth_tl, adoption_worlds = own_effect_in_todays_market(market, hist, pols["truelift"])
    truth_bl, _ = own_effect_in_todays_market(market, hist, blanket)
    tl_quotes, bl_quotes = [q[1] for q in quotes["truelift"]], [q[0] for q in quotes["truelift"]]
    # does the chosen version truly beat the owner's own offer? (TL-018: the best of 34 noisy
    # forecasts flatters itself; this is measured against the truth in today's market)
    sel = [
        (r, q[0], q[1])
        for r, q in enumerate(quotes["truelift"])
        if q[0] is not None and q[1] is not None and q[1]["design"] != q[0]["design"]
    ]
    adv_f = np.array([b["profit_change"] - o["profit_change"] for _, o, b in sel])
    adv_t = np.array([truth_tl["lift_profit"].iloc[r] - truth_bl["lift_profit"].iloc[r] for r, _, _ in sel])
    suggest = np.array([engine.worth_suggesting(o, b) for _, o, b in sel])
    results["selection"] = {
        "rule": engine.selection,
        "restaurants_with_a_different_version": len(sel),
        "share_truly_better_than_owner": round(float((adv_t > 0).mean()), 3) if len(sel) else None,
        "forecast_advantage_total": round(float(adv_f.sum())),
        "true_advantage_total": round(float(adv_t.sum())),
        "suggested_to_owner": int(suggest.sum()),
        "share_of_suggestions_truly_better": round(float((adv_t[suggest] > 0).mean()), 3) if suggest.any() else None,
        "no_offer_chosen": sum(d.discount <= 0 and d.reward <= 0 for d in designs["truelift"]),
    }
    results["forecast"] = {
        "truelift_design_in_todays_market": forecast_check(tl_quotes, truth_tl),
        "owner_blanket_offer_in_todays_market": forecast_check(bl_quotes, truth_bl),
        "truelift_design_after_everyone_switches": forecast_check(tl_quotes, worlds["truelift"]["per_rest"]),
        "owner_blanket_offer_after_everyone_switches": forecast_check(bl_quotes, worlds["today_blanket"]["per_rest"]),
    }
    log("forecast checked against the truth")
    if not with_details:
        return results

    # design mix chosen by TrueLift
    ds = designs["truelift"]
    results["truelift_designs"] = {
        "no_discount": sum(d.discount == 0 for d in ds),
        "brand_pack": sum(d.reward > 0 for d in ds),
        "audience": pd.Series([d.audience for d in ds if d.discount > 0]).value_counts().to_dict(),
        "with_min_order": sum(d.min_order > 0 for d in ds if d.discount > 0),
        "offpeak_only": sum(d.offpeak_only for d in ds if d.discount > 0),
        "depth_share_of_aov": round(
            float(np.mean([d.discount / aov[i] for i, d in enumerate(ds) if d.discount > 0])), 3
        ),
    }

    # weekly measurement, judged against the truth (scripts/measurement_study.py)
    rows = worlds["truelift"]["rows"]
    tl_quotes = [q[1] for q in quotes["truelift"]]
    weekly_el = {r: q["eligible_visits"] for r, q in enumerate(tl_quotes) if q is not None}
    meas = measure_offers(engine, rows, ds, aov, baskets, EVAL_WEEKS, weekly_el)
    results["measurement"] = coverage(meas)
    results["detection"] = {"truelift_offers": detection(meas)}
    log("measurement checked against the truth")

    # decision D7: which noise estimate and which regression adjustment cover the truth best
    variants = []
    for r, g in rows.groupby("rest"):
        d = ds[r]
        if d.discount <= 0:
            continue
        g = g.sort_values("week", kind="stable").reset_index(drop=True)
        v = engine.design_values(g, d, aov[r], baskets[r])
        for upto in (1, 2, 4):
            m = (g["week"] <= upto).to_numpy()
            gg = g[m]
            if gg["shown"].sum() < 10:
                continue
            sh = gg["shown"].to_numpy()
            true_total = float((gg["p"] * gg["profit"] - gg["p_cf"] * gg["profit_cf"]).to_numpy()[sh].sum())
            true_orders = float((gg["p"] - gg["p_cf"]).to_numpy()[sh].sum())
            for var, adj in MEASUREMENT_VARIANTS:
                mv = engine.measure(
                    gg,
                    aov[r],
                    float(v["gain"][m].mean()),
                    float((v["p1"] - v["p0"])[m].mean()),
                    (v["p0"] * v["profit0"])[m],
                    v["p0"][m],
                    variance=var,
                    adjust=adj,
                )
                variants.append(
                    {
                        "variant": f"{var}+{adj}",
                        "weeks": upto,
                        "profit_in": mv["profit"]["low"] <= true_total <= mv["profit"]["high"],
                        "orders_in": mv["orders"]["low"] <= true_orders <= mv["orders"]["high"],
                        "profit_width": mv["profit"]["high"] - mv["profit"]["low"],
                    }
                )
    vt = pd.DataFrame(variants)
    cover = {
        name: {
            f"after_{w}_weeks": {
                "coverage_80_profit": round(float(g2["profit_in"].mean()), 3),
                "coverage_80_orders": round(float(g2["orders_in"].mean()), 3),
                "mean_width_profit": round(float(g2["profit_width"].mean())),
            }
            for w, g2 in g.groupby("weeks")
        }
        for name, g in vt.groupby("variant")
    }
    gap = {
        name: sum(
            abs(c[k] - 0.8) for wk in by_w.values() for k, c in [("coverage_80_profit", wk), ("coverage_80_orders", wk)]
        )
        for name, by_w in cover.items()
    }
    results["measurement_variants"] = {
        "rule": "the variant whose 80% coverage is closest to 80% at weeks 1, 2 and 4, profit and orders (D7)",
        "coverage": cover,
        "closest_to_nominal": min(gap, key=gap.get),
        "in_use": f"{engine.variance}+{engine.adjust}",
    }

    # A/A test: TrueLift's offers as placebos for twelve weekly looks (A04 M2, TL-017)
    aa = run_world(market, hist, replace(pols["truelift"], placebo=True, name="A/A"), keep_rows=True, weeks=AA_WEEKS)
    results["aa_test"] = aa_summary(
        measure_offers(engine, aa["rows"], ds, aov, baskets, AA_WEEKS, weekly_el, placebo=True)
    )
    del aa
    log("A/A test done")

    # owners' blanket offers measured with a control group: fixed 10%, and 30% in weeks 1-2 when
    # the forecast range includes zero (TL-009, A04 M3)
    bl_designs = [Design(float(depth[r])) for r in range(n)]
    bl_quotes = [q[0] for q in quotes["truelift"]]
    weekly_bl = {r: q["eligible_visits"] for r, q in enumerate(bl_quotes) if q is not None}
    blanket_measured = replace(blanket, holdout=engine.holdout, name="today: blanket, measured")
    world = run_world(market, hist, blanket_measured, keep_rows=True)
    bl_records = measure_offers(engine, world["rows"], bl_designs, aov, baskets, EVAL_WEEKS, weekly_bl)
    early_bl = adaptive_holdout(bl_quotes)
    world = run_world(market, hist, blanket_measured, keep_rows=True, holdout_by_week={1: early_bl, 2: early_bl})
    ba_records = measure_offers(engine, world["rows"], bl_designs, aov, baskets, EVAL_WEEKS, weekly_bl)
    early_tl = adaptive_holdout(tl_quotes)
    world_ta = run_world(market, hist, pols["truelift"], keep_rows=True, holdout_by_week={1: early_tl, 2: early_tl})
    ta_records = measure_offers(engine, world_ta["rows"], ds, aov, baskets, EVAL_WEEKS, weekly_el)
    del world
    results["detection"].update(
        {
            "blanket_fixed_holdout": detection(bl_records),
            "blanket_adaptive_holdout": detection(ba_records),
            "truelift_adaptive_holdout": detection(ta_records),
            "adaptive_rule": "30% control group in weeks 1-2 when the forecast range includes zero, then 10%",
            "blanket_offers_with_early_30pct": int((early_bl > 0.1).sum()),
            "truelift_offers_with_early_30pct": int((early_tl > 0.1).sum()),
            # what the larger early control group costs TrueLift's owners (true own-offer profit a week)
            "truelift_own_offer_profit_fixed": round(float(worlds["truelift"]["per_rest"]["lift_profit"].sum())),
            "truelift_own_offer_profit_adaptive": round(float(world_ta["per_rest"]["lift_profit"].sum())),
        }
    )
    del world_ta
    log("detection of losing offers checked")

    # measure-only (A01 I2): today's blanket offers, measured; offers paused or flagged as probably
    # losing by week 4 stop at renewal. Shown on the same customer visits as the other policies.
    stopped = bl_records.loc[
        (bl_records["weeks"] == EVAL_WEEKS[-1]) & bl_records["verdict"].isin(["pause", "probably_losing"]), "rest"
    ].to_numpy()
    mo_pol = replace(blanket_measured, discount=np.where(np.isin(np.arange(n), stopped), 0.0, blanket.discount))
    mo_pol.name = "measure only: losing offers stop at renewal"
    worlds["measure_only"] = run_world(market, hist, mo_pol)
    results["policies"]["measure_only"] = {
        "name": mo_pol.name,
        **summarise(worlds["measure_only"], base),
        "offers_stopped_at_renewal": int(len(stopped)),
    }

    # Zomato's weight in TrueLift's objective: the frontier of restaurant profit against Zomato's
    # contribution (WP-36, A01 I4, A08 B4); lambda = 0 is TrueLift as evaluated above
    frontier = [{"zomato_weight": 0.0, **_point(results["policies"]["truelift"])}]
    for lam in (0.5, 1.0, 2.0):
        ds_l, _ = choose_designs(engine, by_rest, depth, aov, baskets, zomato_weight=lam)
        mx_l = np.array([engine.mix(baskets[r], ds_l[r], aov[r]) for r in range(n)])
        w_l = run_world(market, hist, policy_from_designs(ds_l, engine, mx_l, f"TrueLift, Zomato weight {lam}"))
        frontier.append({"zomato_weight": lam, **_point(summarise(w_l, base))})
    results["zomato_weight_frontier"] = {
        "points": frontier,
        "reference": {k: _point(results["policies"][k]) for k in ("today_blanket", "no_offer", "measure_only")},
    }
    log("Zomato-weight frontier done")

    # OTP consent: owners who stop approving offers (WP-13, A01 I1, A08 B1). Same customer visits.
    rng_a = np.random.default_rng(2026)
    order = rng_a.permutation(n)
    attrition = {"truelift_all_approve": _point(results["policies"]["truelift"])}
    blind = {}
    for share in (0.1, 0.2, 0.3, 0.5):
        out = np.isin(np.arange(n), order[: int(round(share * n))])
        w_a = run_world(market, hist, replace(blanket, discount=np.where(out, 0.0, blanket.discount)))
        blind[share] = _point(summarise(w_a, base))
    attrition["blanket_owners_decline_blind"] = {f"{int(k * 100)}%": v for k, v in blind.items()}
    bl_losers = (worlds["today_blanket"]["per_rest"]["lift_profit"] <= 0).to_numpy()
    w_a = run_world(market, hist, replace(blanket, discount=np.where(bl_losers, 0.0, blanket.discount)))
    attrition["blanket_losing_owners_decline"] = {**_point(summarise(w_a, base)), "owners": int(bl_losers.sum())}
    tl_losers = (worlds["truelift"]["per_rest"]["lift_profit"] <= 0).to_numpy() & (pols["truelift"].discount > 0)
    w_a = run_world(
        market, hist, replace(pols["truelift"], discount=np.where(tl_losers, 0.0, pols["truelift"].discount))
    )
    attrition["truelift_losing_owners_decline"] = {**_point(summarise(w_a, base)), "owners": int(tl_losers.sum())}
    # the blind-decline share at which blanket offers earn Zomato no more commission than TrueLift
    tl_c = results["policies"]["truelift"]["zomato_commission_change"]
    xs = [0.0, *blind]
    ys = [
        results["policies"]["today_blanket"]["zomato_commission_change"],
        *(blind[k]["zomato_commission_change"] for k in blind),
    ]
    attrition["break_even_blind_decline_share"] = _first_at_or_below(xs, ys, tl_c)
    results["consent_attrition"] = attrition
    log("consent attrition scenarios done")

    # Zomato's ledger (WP-14, TL-010, A08 B2, B3, B6): market rows, co-funding, the control group's cost
    P = results["policies"]
    tl, cf = P["truelift"], P["zomato_cofund_naive"]
    extra_new = cf["platform_extra_orders"] - tl["platform_extra_orders"]
    results["zomato_ledger"] = {
        # share of an offer's extra orders that Zomato would not have had at all (the rest moved
        # from other restaurants on Zomato): what the platform gains, as against the restaurant
        "platform_incremental_share_of_extra_orders": {
            k: round(P[k]["platform_extra_orders"] / P[k]["own_offer_extra_orders"], 3)
            for k in ("today_blanket", "rule_new_customers", "truelift", "zomato_cofund_naive")
            if P[k]["own_offer_extra_orders"] > 0
        },
        "cofunding": {
            "extra_zomato_funded_discount": cf["zomato_funded_discount"] - tl["zomato_funded_discount"],
            "extra_platform_incremental_orders": extra_new,
            "cost_per_extra_platform_incremental_order": round(
                (cf["zomato_funded_discount"] - tl["zomato_funded_discount"]) / extra_new
            )
            if extra_new > 0
            else None,
            "contribution_change_vs_truelift": cf["zomato_contribution_change"] - tl["zomato_contribution_change"],
            # the customer sees the same offer whoever pays for it, so co-funding that does not
            # change which offers run creates no order: it moves money from Zomato to restaurants
            "pure_transfer": extra_new <= 0,
        },
        # held-out customers do not get an offer that works on average: the measurement's price
        "control_group_cost_truelift": {
            "holdout_share": engine.holdout,
            "profit_forgone_a_week": round(tl["own_offer_profit_effect"] * engine.holdout / (1 - engine.holdout)),
            "orders_forgone_a_week": round(tl["own_offer_extra_orders"] * engine.holdout / (1 - engine.holdout)),
        },
    }

    # partial adoption: a tenth and three tenths of restaurants use TrueLift, the rest keep today's
    # offers (A06 S4); compared with today's market on the same visits
    today = run_world(market, hist, todays_market(market))
    adoption = {"base": "today's market (a share of restaurants with blanket offers, no holdout)"}
    for k, groups in (("10%", 1), ("30%", 3)):
        mine = np.arange(n) % ADOPTION_GROUPS < groups
        if groups == 1:
            w_p = adoption_worlds[0]  # the first forecast-check world is this one
        else:
            w_p = run_world(market, hist, adopt(todays_market(market), pols["truelift"], mine, f"TrueLift at {k}"))
        d_profit = w_p["per_rest"]["profit"] - today["per_rest"]["profit"]
        adoption[k] = {
            "adopters": int(mine.sum()),
            "adopters_profit_change_a_week": round(float(d_profit[mine].sum())),
            "others_profit_change_a_week": round(float(d_profit[~mine].sum())),
            "zomato_commission_change_a_week": round(
                float((w_p["per_rest"]["commission"] - today["per_rest"]["commission"]).sum())
            ),
            "orders_change_a_week": round(float((w_p["per_rest"]["orders"] - today["per_rest"]["orders"]).sum())),
        }
    results["partial_adoption"] = adoption

    # history that moves during the evaluation (features follow each week; A06 S6)
    moving = run_world(market, hist, pols["truelift"], moving=True)
    results["moving_history"] = {
        "fixed_snapshot": _point(results["policies"]["truelift"]),
        "features_follow_each_week": _point(summarise(moving, base)),
    }
    log("partial adoption and moving history done")

    # fairness (WP-32, A13 F1-F3): who gets discounts, and three mitigations with their cost
    seg = {"today_blanket": worlds["today_blanket"]["segments"], "truelift": worlds["truelift"]["segments"]}
    tl_pol = pols["truelift"]
    reward = np.array([float(design_options(aov[r])["reward"]) if tl_pol.discount[r] > 0 else 0.0 for r in range(n)])
    mitigations = {
        "brand_pack_for_regulars": replace(tl_pol, reward=np.maximum(tl_pol.reward, reward)),
        "regulars_always_eligible": widened(tl_pol, lambda f, m: np.asarray(f["cr_orders_4w"])[m] >= 3),
        "random_20pct_also_shown": widened(
            tl_pol, lambda f, m: stable_uniform(np.asarray(f["cust"])[m], np.asarray(f["rest"])[m], 17) < 0.2
        ),
    }
    costs = {}
    for name, pol in mitigations.items():
        w_m = run_world(market, hist, pol, segments=True)
        seg[name] = w_m["segments"]
        pm = summarise(w_m, base)
        costs[name] = {
            **_point(pm),
            "own_offer_profit_change_vs_truelift": pm["own_offer_profit_effect"] - tl["own_offer_profit_effect"],
        }
    results["fairness"] = {**fairness_report(seg), "mitigations": costs}
    log("fairness report done")

    # control set for the no-offer model (TL-019): every unshown visit (valid here because the
    # shadow phase randomises offer, audience and time) or only the random holdouts
    m_hold = UpliftModel.fit(trained.train, seed=7, control="holdout_only")
    e_hold = Engine(m_hold, terms=engine.terms, topup_value=engine.topup_value)
    e_hold.gain_scale = engine.gain_scale
    v_h = e_hold.row_values(
        rows,
        pols["truelift"].discount[rows["rest"].to_numpy()],
        pols["truelift"].min_order[rows["rest"].to_numpy()],
        pols["truelift"].reward[rows["rest"].to_numpy()],
        0.0,
        tuple(mixes["truelift"][rows["rest"].to_numpy(), i] for i in range(4)),
    )
    up_h = v_h["p1"] - v_h["p0"]
    sh = rows["shown"].to_numpy()
    results["control_set"] = {
        "assumption": "all unshown visits are a valid control set only because the shadow phase randomises "
        "offer, audience and time slot; on observational logs use holdouts only or weight by the known "
        "assignment probabilities",
        "holdout_only": {
            "qini": round(qini_coefficient(up_h, sh, rows["chosen"].to_numpy()), 3),
            "corr_with_true_uplift": round(float(np.corrcoef(up_h[sh], (rows["p"] - rows["p_cf"])[sh])[0, 1]), 3),
            "control_rows": int((trained.train["holdout"]).sum()),
        },
        "all_unshown_in_use": {"control_rows": int((~trained.train["shown"]).sum())},
    }

    # uplift ranking quality on the evaluation weeks (sampled outcomes, random holdout)
    el = rows
    rr = el["rest"].to_numpy()
    v = engine.row_values(
        el,
        pols["truelift"].discount[rr],
        pols["truelift"].min_order[rr],
        pols["truelift"].reward[rr],
        0.0,
        tuple(mixes["truelift"][rr, i] for i in range(4)),
    )
    up = v["p1"] - v["p0"]
    results["uplift_quality"] = {
        "qini_model": round(qini_coefficient(up, el["shown"].to_numpy(), el["chosen"].to_numpy()), 3),
        "corr_with_true_uplift": round(
            float(np.corrcoef(up[el["shown"]], (el["p"] - el["p_cf"])[el["shown"]])[0, 1]), 3
        ),
    }

    # per-restaurant table and the demo restaurant
    pr = {k: worlds[k]["per_rest"] for k in ("no_offer", "today_blanket", "truelift")}
    tab = pd.DataFrame(
        {
            "restaurant_id": range(n),
            "name": [display_name(r) for _, r in R.iterrows()],
            "locality": R["locality"],
            "aov": aov,
            "orders_no_offer": pr["no_offer"]["orders"].round(1),
            "blanket_profit_change": (pr["today_blanket"]["profit"] - pr["no_offer"]["profit"]).round(0),
            "blanket_redemptions": pr["today_blanket"]["redemptions"].round(1),
            "blanket_extra_orders": (pr["today_blanket"]["orders"] - pr["no_offer"]["orders"]).round(1),
            "truelift_profit_change": (pr["truelift"]["profit"] - pr["no_offer"]["profit"]).round(0),
            "truelift_design": [d.label() for d in ds],
            # forecast shown before approval vs the truth when this restaurant switches in today's market
            "truelift_forecast": [q[1]["profit_change"] if q[1] else 0 for q in quotes["truelift"]],
            "truelift_forecast_low": [q[1]["profit_low"] if q[1] else 0 for q in quotes["truelift"]],
            "truelift_forecast_high": [q[1]["profit_high"] if q[1] else 0 for q in quotes["truelift"]],
            "truelift_truth_todays_market": truth_tl["lift_profit"].round(0).to_numpy(),
            "owner_forecast": [q[0]["profit_change"] if q[0] else 0 for q in quotes["truelift"]],
            "owner_truth_todays_market": truth_bl["lift_profit"].round(0).to_numpy(),
        }
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    tab.to_csv(out_dir / "restaurants_results.csv", index=False)
    cand = tab[
        (tab["aov"].between(350, 450))
        & (tab["blanket_profit_change"] < 0)
        & (tab["truelift_profit_change"] > 0)
        & (tab["orders_no_offer"] >= 40)
    ]
    if len(cand):
        demo = int(cand.sort_values("orders_no_offer", ascending=False)["restaurant_id"].iloc[0])
    else:
        demo = int(tab["orders_no_offer"].idxmax())
    results["demo_restaurant"] = tab.loc[demo].to_dict()
    results["blanket_restaurants_losing"] = int((tab["blanket_profit_change"] < 0).sum())
    results["calibration"] = {
        "topup_value": round(engine.topup_value, 3),
        "topup_value_80": [round(v, 3) for v in trained.topup_range],
        "topup_value_simulator_truth": cfg.topup_value,
        "sigma_profit_share_of_aov": round(engine.sigma_rel, 4),
        "sigma_orders_per_visit": round(engine.sigma_orders, 5),
        "shadow_offers": len(offers),
    }
    meas.to_csv(out_dir / "measurement_check.csv", index=False)
    save_bundle(
        trained.bundle(
            demo, ds, version=code_version(), data_sha256=file_sha256(ROOT / "data/processed/restaurants.csv")
        ),
        model_out,
    )
    log(f"done in {time.time() - t0:.0f}s")
    return results


# Headline rows compared across seeds (A06 S1), and the policy pairs whose difference is tested
SEED_METRICS = (
    "offers_that_pay",
    "own_offer_profit_effect",
    "restaurant_profit_change",
    "zomato_commission_change",
    "customer_savings",
)
SEED_PAIRS = (("truelift", "today_blanket"), ("truelift", "rule_new_customers"))
SEED_THREADS = 2  # threads per worker, fixed so a run gives the same numbers on any machine


class Run(NamedTuple):
    """One non-detailed evaluation: a market (Config), commercial terms and TrueLift's holdout."""

    label: str
    cfg: Config
    terms: Terms = Terms()
    holdout: float = 0.10


def _evaluate_quietly(job: Run) -> tuple[str, dict]:
    """One non-detailed evaluation in a worker process (seeds and scenarios run side by side)."""
    from threadpoolctl import threadpool_limits

    with threadpool_limits(limits=SEED_THREADS):
        return job.label, evaluate(job.cfg, False, with_details=False, terms=job.terms, holdout=job.holdout)


def run_parallel(jobs: list[Run], workers: int) -> dict:
    """{label: report} for the jobs, `workers` at a time (1 = one after another in this process).
    Each run is deterministic, so the order and the number of workers do not change any number."""
    if workers <= 1:
        return dict(_evaluate_quietly(j) for j in jobs)
    from concurrent.futures import ProcessPoolExecutor

    with ProcessPoolExecutor(max_workers=workers) as pool:
        return dict(pool.map(_evaluate_quietly, jobs))


def seed_summary(by_seed: dict) -> dict:
    """Mean and standard deviation of each headline row over seeds, and whether each policy
    difference is larger than twice its seed-to-seed standard deviation."""
    rows = {}
    pols = next(iter(by_seed.values()))["policies"]
    for pol in pols:
        rows[pol] = {}
        for m in SEED_METRICS:
            v = np.array([r["policies"][pol][m] for r in by_seed.values()], float)
            rows[pol][m] = {"mean": round(float(v.mean()), 1), "sd": round(float(v.std(ddof=1)), 1)}
    diffs = {}
    for a, b in SEED_PAIRS:
        diffs[f"{a}_minus_{b}"] = {}
        for m in SEED_METRICS:
            d = np.array([r["policies"][a][m] - r["policies"][b][m] for r in by_seed.values()], float)
            sd = float(d.std(ddof=1))
            diffs[f"{a}_minus_{b}"][m] = {
                "per_seed": [round(float(x)) for x in d],
                "mean": round(float(d.mean()), 1),
                "sd": round(sd, 1),
                "exceeds_2_sd": bool(abs(d.mean()) > 2 * sd),
                "same_sign_every_seed": bool((d > 0).all() or (d < 0).all()),
            }
    return {"seeds": [int(k) for k in by_seed], "policies": rows, "differences": diffs}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="fewer customers, no scenarios or seeds (about 2 minutes)")
    ap.add_argument("--out", type=Path, default=ROOT / "reports", help="directory for the report files")
    ap.add_argument(
        "--model-out", type=Path, default=ROOT / "data/processed/model.pkl", help="where to write the model bundle"
    )
    ap.add_argument("--seed", type=int, default=7, help="market seed (customers, tastes, offers, draws)")
    ap.add_argument(
        "--seeds", default="8,9,10,11", help="extra market seeds for the spread (full run only; empty for none)"
    )
    ap.add_argument("--workers", type=int, default=3, help="scenario and seed runs at a time (each needs ~2 GB)")
    args = ap.parse_args()
    started = time.time()
    base_cfg = Config(customers_per_locality=2000, seed=args.seed) if args.quick else Config(seed=args.seed)
    report = {"main": evaluate(base_cfg, args.quick, with_details=True, out_dir=args.out, model_out=args.model_out)}
    if not args.quick:
        ps = base_cfg.price_sensitivity
        jobs = [
            Run("less_price_sensitive", replace(base_cfg, price_sensitivity=tuple(round(s * 0.7, 3) for s in ps))),
            Run("more_price_sensitive", replace(base_cfg, price_sensitivity=tuple(round(s * 1.3, 3) for s in ps))),
            # commission on the price before the discount (A06 S2): blanket offers cost the owner more
            Run("pre_discount_commission", base_cfg, Terms(commission_on="pre_discount")),
        ]
        seeds = [int(x) for x in args.seeds.split(",") if x.strip()]
        jobs += [Run(f"seed_{k}", replace(base_cfg, seed=k)) for k in seeds]
        log(f"scenarios and seeds: {len(jobs)} runs, {args.workers} at a time")
        done = run_parallel(jobs, args.workers)
        for label in ("less_price_sensitive", "more_price_sensitive", "pre_discount_commission"):
            report[label] = done[label]
        if seeds:
            by_seed = {args.seed: report["main"], **{k: done[f"seed_{k}"] for k in seeds}}
            report["seeds"] = {
                **seed_summary(by_seed),
                "by_seed": {
                    str(k): {"policies": r["policies"], "selection": r["selection"]} for k, r in by_seed.items()
                },
            }
    args.out.mkdir(parents=True, exist_ok=True)
    report = {"meta": run_meta(args, base_cfg, started), **report}
    with open(args.out / "evaluation.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print(json.dumps(report["main"]["policies"], indent=1, default=str)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
