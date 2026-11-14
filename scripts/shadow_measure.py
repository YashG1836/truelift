"""Measure offers from exported exposure and order files: the shadow kit (integration blueprint §8).

    python scripts/shadow_measure.py data/sample/exposures.csv data/sample/orders.csv
    python scripts/shadow_measure.py exposures.csv orders.csv --food-cost 0.33 --out result.json

Zomato's engineers can run this on their own logs, in the shapes of docs/events/offer.exposure and
order.placed, without the TrueLift service or its model: for each offer it compares customers who
were shown the offer with the held-out ones, as TrueLift's weekly measurement does (the same
`effect_and_se`, customer-level noise, the always-valid pause boundary and the sample-ratio check).

exposures.csv: offer_id, restaurant_id, customer_id, visit_id, week, assignment (show / control),
  and optionally base_profit (the model's expected profit without the offer, logged at decision
  time; with it the comparison is regression-adjusted and much less noisy).
orders.csv: visit_id, basket, discount, used_offer, and optionally reward, zomato_funded.
The restaurant's profit on each order comes from the commercial terms (commission, GST, food cost),
which the flags set. With only the logs, there is no model prior: the result is the offer's own
evidence, which is what TrueLift's combined estimate leans on more each week.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from truelift.economics import Terms, split  # noqa: E402
from truelift.engine import (  # noqa: E402
    MIN_EVENTS,
    PAUSE_ALPHA,
    PAUSE_MIN_CONTROL,
    PROBABLY_LOSING,
    Z80,
    cs_halfwidth,
    cs_rho,
    effect_and_se,
    normal_cdf,
    sample_ratio,
)


def visit_rows(exposures: pd.DataFrame, orders: pd.DataFrame, terms: Terms) -> pd.DataFrame:
    """One row per eligible visit: shown or held out, whether it ordered, and the order's profit."""
    e = exposures[exposures["assignment"].isin(["show", "control"])].copy()
    o = orders.copy()
    for col in ("reward", "zomato_funded"):
        if col not in o:
            o[col] = 0.0
    total = o["discount"] + o["reward"]
    share = np.divide(o["zomato_funded"], total, out=np.zeros(len(o)), where=total > 0)
    o["profit"] = split(o["basket"].to_numpy(float), total.to_numpy(float), share, terms)["restaurant_profit"]
    df = e.merge(o[["visit_id", "basket", "discount", "used_offer", "profit"]], on="visit_id", how="left")
    df["shown"] = (df["assignment"] == "show").to_numpy()
    df["holdout"] = (df["assignment"] == "control").to_numpy()
    df["chosen"] = df["profit"].notna().to_numpy()
    df["takes"] = df["used_offer"].fillna(False).astype(bool).to_numpy()
    df["cust"] = df["customer_id"]
    for col in ("basket", "discount", "profit"):
        df[col] = df[col].fillna(0.0)
    return df.sort_values(["week", "visit_id"], kind="stable").reset_index(drop=True)


def own_estimate(rows: pd.DataFrame) -> dict:
    """The offer's own evidence so far: extra profit and orders per shown visit, and in total."""
    t, c = rows["shown"].to_numpy(), rows["holdout"].to_numpy()
    cust = rows["cust"].to_numpy()
    chosen = rows["chosen"].to_numpy().astype(float)
    base = rows["base_profit"].to_numpy(float) if "base_profit" in rows and rows["base_profit"].notna().all() else None
    n_t = int(t.sum())
    out: dict = {"shown_visits": n_t, "control_visits": int(c.sum()), "regression_adjusted": base is not None}
    for key, y, b in (("profit", chosen * rows["profit"].to_numpy(float), base), ("orders", chosen, None)):
        # the estimate always; its range only once each group has MIN_EVENTS orders (a handful of
        # orders gives an erratic noise estimate, which is why the service leans on its model then)
        est, se = effect_and_se(y, t, c, cust, b, by_customer=True, adjust="fixed", min_events=0)
        measurable = min(np.count_nonzero(chosen[t]), np.count_nonzero(chosen[c])) >= MIN_EVENTS
        finite = math.isfinite(se) and measurable
        out[key] = {
            "measurable": measurable,
            "per_visit": est,
            "se_per_visit": se if finite else None,
            "total": est * n_t,
            "low": (est - Z80 * se) * n_t if finite else None,
            "high": (est + Z80 * se) * n_t if finite else None,
            "chance_positive": normal_cdf(est / se) if finite and se > 0 else None,
        }
    return out


def verdict(rows: pd.DataFrame, est: dict, planned_shown_visits: float, holdout: float) -> dict:
    """Keep / wait / probably losing / pause on the offer's own evidence (no model prior)."""
    p = est["profit"]
    srm = sample_ratio(rows, holdout)
    upper = math.inf
    held = len(np.unique(rows["cust"].to_numpy()[rows["holdout"].to_numpy()]))
    if p["se_per_visit"] is not None and est["shown_visits"] > 0 and held >= PAUSE_MIN_CONTROL:
        n_t = est["shown_visits"]
        planned = max(planned_shown_visits, n_t, 1)
        rho = cs_rho(p["se_per_visit"] * math.sqrt(n_t / planned), planned)
        upper = p["per_visit"] + cs_halfwidth(p["se_per_visit"], n_t, rho)
    if not srm["ok"]:
        code = "check_failed"
    elif upper < 0:
        code = "pause"
    elif p["low"] is not None and p["low"] > 0:
        code = "keep"
    elif p["chance_positive"] is not None and 1 - p["chance_positive"] > PROBABLY_LOSING:
        code = "probably_losing"
    else:
        code = "wait"
    return {"verdict": code, "sample_ratio": srm, "pause_alpha": PAUSE_ALPHA}


def measure_files(exposures: pd.DataFrame, orders: pd.DataFrame, terms: Terms, holdout: float, weeks: int) -> list:
    out = []
    for oid, ex in exposures.groupby("offer_id", sort=True):
        rows = visit_rows(ex, orders, terms)
        last = int(rows["week"].max())
        weekly = []
        for w in range(1, last + 1):
            r = rows[rows["week"] <= w].reset_index(drop=True)
            est = own_estimate(r)
            per_week = est["shown_visits"] / w
            weekly.append({"week": w, **est, **verdict(r, est, per_week * weeks, holdout)})
        out.append({"offer_id": int(oid), "restaurant_id": int(ex["restaurant_id"].iloc[0]), "weeks": weekly})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Measure offers from exposure and order logs")
    ap.add_argument("exposures", type=Path)
    ap.add_argument("orders", type=Path)
    ap.add_argument("--commission", type=float, default=Terms.commission_rate)
    ap.add_argument("--gst", type=float, default=Terms.gst_on_commission)
    ap.add_argument("--food-cost", type=float, default=Terms.food_cost_share)
    ap.add_argument("--commission-on", choices=["post_discount", "pre_discount"], default=Terms.commission_on)
    ap.add_argument("--holdout", type=float, default=0.10, help="planned share held out")
    ap.add_argument("--weeks", type=int, default=4, help="weeks an approval lasts (for the pause boundary)")
    ap.add_argument("--out", type=Path, help="write the full result as JSON")
    a = ap.parse_args()
    terms = Terms(
        commission_rate=a.commission,
        gst_on_commission=a.gst,
        food_cost_share=a.food_cost,
        commission_on=a.commission_on,
    )
    res = measure_files(pd.read_csv(a.exposures), pd.read_csv(a.orders), terms, a.holdout, a.weeks)
    for off in res:
        w = off["weeks"][-1]
        p = w["profit"]
        rng = f"{p['low']:+,.0f} to {p['high']:+,.0f}" if p["low"] is not None else "not yet measurable"
        print(
            f"offer {off['offer_id']} (restaurant {off['restaurant_id']}), week {w['week']}: extra profit "
            f"{p['total']:+,.0f} Rs (80% range {rng}), extra orders {w['orders']['total']:+.1f}, "
            f"{w['shown_visits']} shown / {w['control_visits']} held-out visits, verdict {w['verdict']}"
        )
    if a.out:
        a.out.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
