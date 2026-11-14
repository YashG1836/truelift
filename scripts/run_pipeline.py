"""End-to-end pipeline: simulate history, train, calibrate, compare policies, check measurement.

    .venv/bin/python scripts/run_pipeline.py            # full run, writes model + reports
    .venv/bin/python scripts/run_pipeline.py --quick    # fewer customers, for a fast check

Steps
 1. History: 4 weeks of today's market + 4 weeks of TrueLift's shadow phase (random designs, 10%
    random holdout). This is the only data the models see.
 2. Train the uplift model; calibrate its error with cross-fitting (each restaurant's error is
    measured by a model that never saw that restaurant).
 3. Evaluate 4 weeks under each policy, all restaurants at once, identical customer visits:
    no offer | today (blanket ~15% off for everyone) | rule (new customers only) |
    TrueLift (same discount size as today, TrueLift picks who sees it and the minimum order) |
    TrueLift with Zomato paying half the discount for customers new to Zomato (unmeasured).
    The simulator knows the truth, so every number below is the true expected value.
 4. Measurement check: TrueLift's weekly estimates vs the truth (error and 80% range coverage).
 5. Sensitivity: repeat 3 with customers 30% less and 30% more price-sensitive.
Outputs: data/processed/model.pkl, reports/evaluation.json, reports/evaluation.md
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

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from truelift.economics import Terms  # noqa: E402
from truelift.engine import Design, Engine  # noqa: E402
from truelift.model import file_sha256, library_versions, qini_coefficient, save_bundle  # noqa: E402
from truelift.sim import Config, Market, Policy, display_name, recent_visits  # noqa: E402
from truelift.training import train as train_model  # noqa: E402

EVAL_WEEKS = (1, 2, 3, 4)


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


def run_meta(args: argparse.Namespace, cfg: Config, started: float) -> dict:
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
        "command": "python scripts/run_pipeline.py " + " ".join(sys.argv[1:]),
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "wall_seconds": round(time.time() - started),
        "python": platform.python_version(),
        "libraries": library_versions(),
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "seed": cfg.seed,
        "quick": bool(args.quick),
        "config": asdict(cfg),
        "terms": asdict(Terms()),
        "restaurants_csv_sha256": file_sha256(ROOT / "data/processed/restaurants.csv"),
    }


def run_world(market: Market, hist, policy: Policy, keep_rows: bool = False) -> dict:
    """Four evaluation weeks under one policy. Returns true expected totals (and rows if asked)."""
    per_rest, swiggy, kept = [], [], []
    for w in EVAL_WEEKS:
        occ = market.occasions(w)
        res = market.run_week(occ, policy, market.flat_features(hist, occ), salt=3, truth=True)
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
                "platform_lift": np.where(sh, res["platform_lift"], 0.0),
            }
        )
        per_rest.append(df.groupby("rest").sum())
        first = np.r_[True, res["occ"][1:] != res["occ"][:-1]]
        swiggy.append(pd.DataFrame({"type": res["type"][first], "p_swiggy": res["p_swiggy"][first]}))
        if keep_rows:
            m = res["eligible"]
            kept.append(
                pd.DataFrame(
                    {k: (v[m] if isinstance(v, np.ndarray) and len(v) == len(m) else v) for k, v in res.items()}
                )
            )
    pr = sum(per_rest) / len(EVAL_WEEKS)  # weekly averages per restaurant
    sw = pd.concat(swiggy)
    out = {
        "per_rest": pr.reindex(range(market.n_rest), fill_value=0.0),
        "swiggy_share": float(sw["p_swiggy"].mean()),
        "swiggy_share_loyal": float(sw.loc[sw["type"] == 0, "p_swiggy"].mean()),
    }
    if keep_rows:
        out["rows"] = pd.concat(kept, ignore_index=True)
    return out


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
        0.10,
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
) -> dict:
    t0 = time.time()
    R = pd.read_csv(ROOT / "data/processed/restaurants.csv")
    market = Market(R, cfg, Terms())
    n = market.n_rest
    aov = market.aov
    trained = train_model(market, log)
    hist, baskets, engine, offers = trained.hist, trained.baskets, trained.engine, trained.offers

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
    rule = replace(blanket, audience=np.array(["new_to_restaurant"] * n, dtype=object), name="rule: new customers")
    visits = recent_visits(market, hist)
    by_rest = dict(tuple(visits.groupby("rest")))
    results, designs = {}, {}
    for key, zshare in (("truelift", 0.0), ("truelift_cofund", 0.5)):
        chosen = []
        for r in range(n):
            x = by_rest.get(r)
            owner = Design(float(depth[r]), zomato_share=zshare)
            if x is None:
                chosen.append(Design(0.0))
                continue
            _, best = engine.best_design(x.drop(columns=["rest", "cust"]), owner, aov[r], baskets[r], weeks=2)
            d = Design(**best["design"])
            if best["profit_change"] <= 0:
                d = Design(0.0)
            chosen.append(d)
        designs[key] = chosen
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
        worlds[k] = run_world(market, hist, pol, keep_rows=(with_details and k == "truelift"))
    base = worlds["no_offer"]
    results["policies"] = {k: {"name": pols[k].name, **summarise(w, base)} for k, w in worlds.items()}
    log("policies evaluated")
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

    # measurement accuracy in the TrueLift world (cumulative after 1, 2 and 4 weeks)
    rows = worlds["truelift"]["rows"]
    meas = []
    for r, g in rows.groupby("rest"):
        d = ds[r]
        if d.discount <= 0:
            continue
        for upto in (1, 2, 4):
            gg = g[g["week"] <= upto]
            if gg["shown"].sum() < 10:
                continue
            v = engine.design_values(gg.reset_index(drop=True), d, aov[r], baskets[r])
            m = engine.measure(
                gg, aov[r], float(v["gain"].mean()), float((v["p1"] - v["p0"]).mean()), v["p0"] * v["profit0"], v["p0"]
            )
            sh = gg["shown"].to_numpy()
            true_total = float((gg["p"] * gg["profit"] - gg["p_cf"] * gg["profit_cf"]).to_numpy()[sh].sum())
            true_orders = float((gg["p"] - gg["p_cf"]).to_numpy()[sh].sum())
            p = m["profit"]
            meas.append(
                {
                    "rest": r,
                    "weeks": upto,
                    "true_profit": true_total,
                    "est_profit": p["total"],
                    "low": p["low"],
                    "high": p["high"],
                    "own_only": p["own_per_visit"] * m["shown_visits"],
                    "model_only": p["model_per_visit"] * m["shown_visits"],
                    "w_own": p["weight_on_own_data"],
                    "true_orders": true_orders,
                    "est_orders": m["orders"]["total"],
                    "orders_low": m["orders"]["low"],
                    "orders_high": m["orders"]["high"],
                    "redemptions": m["report_today"]["orders_with_offer"],
                }
            )
    meas = pd.DataFrame(meas)
    acc = {}
    for upto, g in meas.groupby("weeks"):
        acc[f"after_{upto}_weeks"] = {
            "offers": len(g),
            "coverage_80": round(float(((g["true_profit"] >= g["low"]) & (g["true_profit"] <= g["high"])).mean()), 3),
            "coverage_80_orders": round(
                float(((g["true_orders"] >= g["orders_low"]) & (g["true_orders"] <= g["orders_high"])).mean()), 3
            ),
            "mae_combined": round(float((g["est_profit"] - g["true_profit"]).abs().mean())),
            "mae_own_holdout_only": round(float((g["own_only"] - g["true_profit"]).abs().mean())),
            "mae_model_only": round(float((g["model_only"] - g["true_profit"]).abs().mean())),
            "mean_weight_on_own_data": round(float(g["w_own"].mean()), 3),
            "verdict_right_sign": round(float((np.sign(g["est_profit"]) == np.sign(g["true_profit"])).mean()), 3),
            # the decisions the owner sees: keep (range above 0), auto-pause (range below 0), wait
            "said_keep": int((g["low"] > 0).sum()),
            "said_keep_and_truly_positive": int(((g["low"] > 0) & (g["true_profit"] > 0)).sum()),
            "said_pause": int((g["high"] < 0).sum()),
            "said_pause_and_truly_negative": int(((g["high"] < 0) & (g["true_profit"] < 0)).sum()),
            "said_wait": int(((g["low"] <= 0) & (g["high"] >= 0)).sum()),
        }
    results["measurement"] = acc

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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="fewer customers, no sensitivity runs (about a minute)")
    ap.add_argument("--out", type=Path, default=ROOT / "reports", help="directory for the report files")
    ap.add_argument(
        "--model-out", type=Path, default=ROOT / "data/processed/model.pkl", help="where to write the model bundle"
    )
    ap.add_argument("--seed", type=int, default=7, help="market seed (customers, tastes, offers, draws)")
    args = ap.parse_args()
    started = time.time()
    base_cfg = Config(customers_per_locality=2000, seed=args.seed) if args.quick else Config(seed=args.seed)
    report = {"main": evaluate(base_cfg, args.quick, with_details=True, out_dir=args.out, model_out=args.model_out)}
    if not args.quick:
        for label, f in (("less_price_sensitive", 0.7), ("more_price_sensitive", 1.3)):
            cfg = replace(base_cfg, price_sensitivity=tuple(round(s * f, 3) for s in base_cfg.price_sensitivity))
            log(f"sensitivity: {label}")
            report[label] = evaluate(cfg, False, with_details=False, out_dir=args.out, model_out=args.model_out)
    args.out.mkdir(parents=True, exist_ok=True)
    report = {"meta": run_meta(args, base_cfg, started), **report}
    with open(args.out / "evaluation.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print(json.dumps(report["main"]["policies"], indent=1, default=str)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
