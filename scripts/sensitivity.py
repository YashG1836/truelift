"""One-at-a-time sensitivity sweep (audit A06 S3): eight assumptions, each at a low and a high value.

    python scripts/sensitivity.py                 # 17 quick runs, 3 at a time -> reports/sensitivity.json
    python scripts/sensitivity.py --workers 1     # one after another (same numbers, slower)

Every run is the quick market (2,000 customers per locality, seed 7) with one assumption moved and
everything else at its base value; the base run is part of the sweep, so each bar of the tornado
is a difference between two runs that differ in one thing only. Outputs per run, per week:

  offers_that_pay      TrueLift minus today's blanket offers (offers that pay for themselves)
  own_offer_profit     TrueLift minus the simple rule (new customers only): restaurants' profit
                       from their own offers, the owner's view
  restaurant_profit    TrueLift minus the rule, market-wide against a world with no offers
  zomato_commission    TrueLift minus blanket offers, Zomato's commission

A result that changes sign at one end of a range is a boundary of the claim, and is listed
under "boundaries" in plain words.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from run_pipeline import Run, log, run_meta, run_parallel  # noqa: E402

from truelift.economics import Terms  # noqa: E402
from truelift.sim import TYPES, Config  # noqa: E402

QUICK = Config(customers_per_locality=2000, seed=7)
OUTPUTS = {
    "offers_that_pay": ("offers_that_pay", "today_blanket"),
    "own_offer_profit": ("own_offer_profit_effect", "rule_new_customers"),
    "restaurant_profit": ("restaurant_profit_change", "rule_new_customers"),
    "zomato_commission": ("zomato_commission_change", "today_blanket"),
}


def deal_seeker_share(cfg: Config, share: float) -> Config:
    """Set the share of deal-seekers and rescale the other customer types to keep their mix."""
    i = TYPES.index("deal_seeker")
    rest = 1.0 - cfg.type_share[i]
    shares = [round(s * (1.0 - share) / rest, 4) if k != i else share for k, s in enumerate(cfg.type_share)]
    shares[0] = round(1.0 - sum(shares[1:]), 4)  # exact total of one
    return replace(cfg, type_share=tuple(shares))


def scaled_sensitivity(cfg: Config, f: float) -> Config:
    return replace(cfg, price_sensitivity=tuple(round(s * f, 3) for s in cfg.price_sensitivity))


# parameter: (label, unit, base value, [(value, Run)] for low and high)
def sweep(base: Config) -> dict:
    t = Terms()
    return {
        "price_sensitivity": (
            "Price sensitivity of every customer type",
            "x base",
            1.0,
            [(f, Run(f"price_sensitivity={f}", scaled_sensitivity(base, f))) for f in (0.7, 1.3)],
        ),
        "food_cost_share": (
            "Food cost, share of the menu price",
            "share",
            t.food_cost_share,
            [(v, Run(f"food_cost_share={v}", base, replace(t, food_cost_share=v))) for v in (0.30, 0.45)],
        ),
        "commission_rate": (
            "Zomato's commission rate",
            "share",
            t.commission_rate,
            [(v, Run(f"commission_rate={v}", base, replace(t, commission_rate=v))) for v in (0.18, 0.30)],
        ),
        "swiggy_saving": (
            "Typical saving on Swiggy at a similar restaurant",
            "Rs",
            base.swiggy_saving,
            [(v, Run(f"swiggy_saving={v}", replace(base, swiggy_saving=v))) for v in (0.0, 80.0)],
        ),
        "deal_seeker_share": (
            "Share of customers who are deal-seekers",
            "share",
            base.type_share[TYPES.index("deal_seeker")],
            [(v, Run(f"deal_seeker_share={v}", deal_seeker_share(base, v))) for v in (0.10, 0.35)],
        ),
        "holdout_share": (
            "TrueLift's holdout share",
            "share",
            0.10,
            [(v, Run(f"holdout_share={v}", base, t, v)) for v in (0.05, 0.20)],
        ),
        "menus_per_occasion": (
            "Menus a customer opens per ordering occasion",
            "menus",
            base.menus_per_occasion,
            [(v, Run(f"menus_per_occasion={v}", replace(base, menus_per_occasion=v))) for v in (5, 12)],
        ),
        "topup_value": (
            "Value a customer puts on topping up to a minimum order",
            "share",
            base.topup_value,
            [(v, Run(f"topup_value={v}", replace(base, topup_value=v))) for v in (0.3, 0.7)],
        ),
    }


def outputs(report: dict) -> dict:
    p = report["policies"]
    return {k: p["truelift"][m] - p[other][m] for k, (m, other) in OUTPUTS.items()}


def diagnostics(report: dict) -> dict:
    """Why an output moved: the forecast against the truth in today's market, and the advantage
    TrueLift's suggested versions were forecast to have over the owners' offers against their true
    advantage (a boundary where the forecast runs high shows up here first)."""
    f = report["forecast"]["truelift_design_in_todays_market"]
    s = report["selection"]
    return {
        "forecast_to_truth_todays_market": f.get("ratio_forecast_to_truth"),
        "forecast_coverage_80": f.get("coverage_80"),
        "suggested_versions": s["restaurants_with_a_different_version"],
        "share_truly_better_than_owner": s["share_truly_better_than_owner"],
        "forecast_advantage_total": s["forecast_advantage_total"],
        "true_advantage_total": s["true_advantage_total"],
    }


def boundaries(params: dict) -> list[str]:
    """Plain statements of every output that changes sign somewhere in the sweep."""
    words = {
        "offers_that_pay": "TrueLift has more offers that pay than blanket offers",
        "own_offer_profit": "TrueLift earns restaurants more from their own offers than the simple rule",
        "restaurant_profit": "TrueLift leaves restaurants better off than the simple rule, market-wide",
        "zomato_commission": "TrueLift earns Zomato more commission than blanket offers",
    }
    out = []
    for p in params.values():
        base = p["base"]["outputs"]
        for end in ("low", "high"):
            got = p[end]["outputs"]
            for k, sentence in words.items():
                if (base[k] > 0) != (got[k] > 0):
                    status = "no longer holds" if base[k] > 0 else "starts to hold"
                    out.append(f"{sentence}: {status} when {p['label'].lower()} is {p[end]['value']} ({k} {got[k]:+,})")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=ROOT / "reports", help="directory for sensitivity.json")
    ap.add_argument("--workers", type=int, default=3, help="runs at a time (each needs about 1.5 GB)")
    args = ap.parse_args()
    args.quick, args.seeds = True, ""  # for run_meta
    started = time.time()
    spec = sweep(QUICK)
    jobs = [Run("base", QUICK)] + [run for _, _, _, ends in spec.values() for _, run in ends]
    log(f"sensitivity sweep: {len(jobs)} quick runs, {args.workers} at a time")
    done = run_parallel(jobs, args.workers)

    def entry(label: str, value) -> dict:
        r = done[label]
        return {"value": value, "outputs": outputs(r), "diagnostics": diagnostics(r), "policies": r["policies"]}

    params = {}
    for key, (label, unit, base_value, ends) in spec.items():
        params[key] = {"label": label, "unit": unit, "base": entry("base", base_value)}
        for end, (value, run) in zip(("low", "high"), ends, strict=True):
            params[key][end] = entry(run.label, value)
    report = {
        "meta": run_meta(args, QUICK, started),
        "outputs": {k: f"TrueLift minus {other}: {m}" for k, (m, other) in OUTPUTS.items()},
        "parameters": params,
        "boundaries": boundaries(params),
        "base_config": asdict(QUICK),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "sensitivity.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    log(f"wrote {args.out / 'sensitivity.json'}; {len(report['boundaries'])} boundaries")
    for b in report["boundaries"]:
        print(" -", b)
    return 0


if __name__ == "__main__":
    sys.exit(main())
