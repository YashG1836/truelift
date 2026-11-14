"""How well the weekly measurement works, judged against the simulator's truth.

Used by run_pipeline.py on several worlds: TrueLift's offers with the 10% control group; the same
offers as placebos (A/A: shown and held out as usual but with no effect, so every "keep" or
"pause" is a false alarm); owners' blanket offers measured with a 10% control group; and both with
an adaptive control group (30% in weeks 1-2 when the forecast range includes zero, then 10%).

Every offer is measured after each week with the service's own `Engine.measure`, so these numbers
describe the code an owner would see. Audit items: TL-009 (detection), TL-017 (repeated looks),
A04 M2 (A/A and sample ratio), M3 and M4 (adaptive control group, pooled priors), WP-15.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from truelift.engine import Design, Engine

POOL_PSEUDO_OFFERS = 30.0  # a price band's own correction counts as much as 30 offers' worth of global


def _prior_and_base(engine: Engine, g: pd.DataFrame, d: Design, aov: float, baskets, placebo: bool):
    v = engine.design_values(g, d, aov, baskets)
    if placebo:  # the placebo's honest prior is zero effect; the no-offer prediction still adjusts
        gain = np.zeros(len(g))
        uplift = np.zeros(len(g))
    else:
        gain, uplift = v["gain"], v["p1"] - v["p0"]
    return gain, uplift, v["p0"] * v["profit0"], v["p0"]


def measure_offers(
    engine: Engine,
    rows: pd.DataFrame,
    designs: list[Design],
    aov: np.ndarray,
    baskets: list,
    horizons=(1, 2, 3, 4),
    weekly_eligible: dict | None = None,
    consent_weeks: int = 4,
    placebo: bool = False,
    pooled: bool = True,
) -> pd.DataFrame:
    """One record per (offer, weeks so far): truth, estimate, range, verdicts (new rules, and the
    rule used before: pause when the whole 80% range is below zero)."""
    prepared = {}
    for r, g in rows.groupby("rest"):
        d = designs[int(r)]
        if d.discount <= 0 and d.reward <= 0:
            continue
        g = g.sort_values("week", kind="stable").reset_index(drop=True)
        prepared[int(r)] = (g, d, *_prior_and_base(engine, g, d, float(aov[int(r)]), baskets[int(r)], placebo))
    out = []
    for upto in horizons:
        first = {}
        for r, (g, d, gain, uplift, base_p, base_o) in prepared.items():
            m = (g["week"] <= upto).to_numpy()
            gg = g[m]
            if gg["shown"].sum() < 10 or gg["holdout"].sum() < 2:
                continue
            per_week = (weekly_eligible or {}).get(r, len(gg) / upto)
            sigma = engine.sigma_for(d, per_week, float(aov[r]))
            planned = per_week * consent_weeks * (1 - engine.holdout)
            args = (gg, float(aov[r]), float(gain[m].mean()), float(uplift[m].mean()), base_p[m], base_o[m])
            meas = engine.measure(*args, sigma=sigma, planned_shown_visits=planned)
            first[r] = (args, sigma, planned, meas)
        # pooled correction of the model's prior, learned from every other running offer's control
        # group: leave-one-out, by price band, shrunk towards the global value
        shifts = _pooled_shifts(first, aov) if pooled and not placebo else {}
        for r, (args, sigma, planned, meas0) in first.items():
            meas = (
                engine.measure(*args, sigma=sigma, planned_shown_visits=planned, prior_shift=shifts[r])
                if r in shifts
                else meas0
            )
            gg = args[0]
            sh = gg["shown"].to_numpy()
            if placebo:
                true_p = true_o = 0.0
            else:
                true_p = float((gg["p"] * gg["profit"] - gg["p_cf"] * gg["profit_cf"]).to_numpy()[sh].sum())
                true_o = float((gg["p"] - gg["p_cf"]).to_numpy()[sh].sum())
            p, o = meas["profit"], meas["orders"]
            old = meas0["profit"]
            out.append(
                {
                    "rest": r,
                    "weeks": upto,
                    "true_profit": true_p,
                    "true_orders": true_o,
                    "est_profit": p["total"],
                    "low": p["low"],
                    "high": p["high"],
                    "own_only": p["own_per_visit"] * meas["shown_visits"],
                    "model_only": p["model_per_visit"] * meas["shown_visits"],
                    "w_own": p["weight_on_own_data"],
                    "prob_positive": p["prob_positive"],
                    "est_orders": o["total"],
                    "orders_low": o["low"],
                    "orders_high": o["high"],
                    "redemptions": meas["report_today"]["orders_with_offer"],
                    "verdict": meas["verdict_code"],
                    "verdict_unpooled": meas0["verdict_code"],
                    "old_rule": "pause" if old["high"] < 0 else "keep" if old["low"] > 0 else "wait",
                    "srm_ok": bool(meas["sample_ratio"]["ok"]),
                    "est_profit_unpooled": old["total"],
                    "low_unpooled": old["low"],
                    "high_unpooled": old["high"],
                }
            )
    return pd.DataFrame(out)


def _pooled_shifts(first: dict, aov: np.ndarray) -> dict:
    rec = []
    for r, (_, sigma, _, meas) in first.items():
        p, o = meas["profit"], meas["orders"]
        if p["own_se"] is None or o["own_se"] is None:
            continue
        a = float(aov[r])
        rec.append(
            {
                "rest": r,
                "band": 0 if a < 300 else 1 if a < 500 else 2,
                "aov": a,
                "dp": (p["own_per_visit"] - p["model_per_visit"]) / a,
                "wp": 1.0 / ((p["own_se"] ** 2 + sigma[0] ** 2) / a**2),
                "do": o["own_per_visit"] - o["model_per_visit"],
                "wo": 1.0 / (o["own_se"] ** 2 + sigma[1] ** 2),
            }
        )
    if len(rec) < 20:
        return {}
    df = pd.DataFrame(rec)
    shifts = {}
    for d_col, w_col in (("dp", "wp"), ("do", "wo")):
        wd, w = df[d_col] * df[w_col], df[w_col]
        glob = (wd.sum() - wd) / (w.sum() - w)  # leave this offer out
        band_wd = df.assign(x=wd).groupby("band")["x"].transform("sum")
        band_w = df.assign(x=w).groupby("band")["x"].transform("sum")
        band_n = df.groupby("band")["rest"].transform("size") - 1
        band_mean = (band_wd - wd) / (band_w - w).where(band_w - w > 0, np.nan)
        k = POOL_PSEUDO_OFFERS
        shrunk = (band_n * band_mean.fillna(glob) + k * glob) / (band_n + k)
        df[d_col + "_shift"] = shrunk
    for row in df.itertuples():
        shifts[int(row.rest)] = (float(row.dp_shift) * row.aov, float(row.do_shift))
    return shifts


def coverage(records: pd.DataFrame) -> dict:
    out = {}
    for w, g in records.groupby("weeks"):
        out[f"after_{w}_weeks"] = {
            "offers": len(g),
            "coverage_80": round(float(((g["true_profit"] >= g["low"]) & (g["true_profit"] <= g["high"])).mean()), 3),
            "coverage_80_orders": round(
                float(((g["true_orders"] >= g["orders_low"]) & (g["true_orders"] <= g["orders_high"])).mean()), 3
            ),
            "coverage_80_without_pooling": round(
                float(((g["true_profit"] >= g["low_unpooled"]) & (g["true_profit"] <= g["high_unpooled"])).mean()), 3
            ),
            "mae_combined": round(float((g["est_profit"] - g["true_profit"]).abs().mean())),
            "mae_without_pooling": round(float((g["est_profit_unpooled"] - g["true_profit"]).abs().mean())),
            "mae_own_holdout_only": round(float((g["own_only"] - g["true_profit"]).abs().mean())),
            "mae_model_only": round(float((g["model_only"] - g["true_profit"]).abs().mean())),
            "misses_below": int((g["true_profit"] < g["low"]).sum()),
            "misses_above": int((g["true_profit"] > g["high"]).sum()),
            "mean_weight_on_own_data": round(float(g["w_own"].mean()), 3),
            "verdict_right_sign": round(float((np.sign(g["est_profit"]) == np.sign(g["true_profit"])).mean()), 3),
            "verdicts": {k: int(v) for k, v in g["verdict"].value_counts().items()},
            "verdicts_rule_before": {k: int(v) for k, v in g["old_rule"].value_counts().items()},
            "said_keep_and_truly_positive": int(((g["verdict"] == "keep") & (g["true_profit"] > 0)).sum()),
            "said_pause_and_truly_negative": int(((g["verdict"] == "pause") & (g["true_profit"] < 0)).sum()),
            "sample_ratio_flags": int((~g["srm_ok"]).sum()),
        }
    return out


def detection(records: pd.DataFrame, horizon: int | None = None) -> dict:
    """For offers that truly lose money by the end of the consent period: the share flagged, week
    by week; and for offers that truly make money, the share paused (false pauses)."""
    if records.empty:
        return {}
    last = int(horizon or records["weeks"].max())
    final = records[records["weeks"] == last].set_index("rest")["true_profit"]
    losing, winning = set(final.index[final < 0]), set(final.index[final > 0])
    out = {"truly_losing_offers": len(losing), "truly_profitable_offers": len(winning), "by_week": {}}
    ever_new, ever_old = set(), set()
    for w, g in records.groupby("weeks"):
        g = g.set_index("rest")
        lose = g[g.index.isin(losing)]
        win = g[g.index.isin(winning)]
        ever_new |= set(g.index[g["verdict"] == "pause"])
        ever_old |= set(g.index[g["old_rule"] == "pause"])
        out["by_week"][f"week_{w}"] = {
            "losing_paused": round(float((lose["verdict"] == "pause").mean()), 3) if len(lose) else None,
            "losing_paused_or_warned": round(float(lose["verdict"].isin(["pause", "probably_losing"]).mean()), 3)
            if len(lose)
            else None,
            "losing_paused_rule_before": round(float((lose["old_rule"] == "pause").mean()), 3) if len(lose) else None,
            "profitable_paused": round(float((win["verdict"] == "pause").mean()), 3) if len(win) else None,
            "profitable_paused_rule_before": round(float((win["old_rule"] == "pause").mean()), 3) if len(win) else None,
            "profitable_ever_paused": round(len(ever_new & winning) / max(len(winning), 1), 3),
            "profitable_ever_paused_rule_before": round(len(ever_old & winning) / max(len(winning), 1), 3),
        }
    return out


def aa_summary(records: pd.DataFrame) -> dict:
    """A/A world: the true effect is zero, so every keep, warning or pause is a false alarm."""
    out = {"offers": int(records["rest"].nunique()), "by_week": {}}
    ever_pause, ever_keep = set(), set()
    for w, g in records.groupby("weeks"):
        ever_pause |= set(g.loc[g["verdict"] == "pause", "rest"])
        ever_keep |= set(g.loc[g["verdict"] == "keep", "rest"])
        n = g["rest"].nunique()
        out["by_week"][f"week_{w}"] = {
            "covers_zero": round(float(((g["low"] <= 0) & (g["high"] >= 0)).mean()), 3),
            "own_estimate_mean_per_offer": round(float(g["own_only"].mean()), 1),
            "said_keep": round(float((g["verdict"] == "keep").mean()), 3),
            "said_probably_losing": round(float((g["verdict"] == "probably_losing").mean()), 3),
            "said_pause": round(float((g["verdict"] == "pause").mean()), 3),
            "said_pause_rule_before": round(float((g["old_rule"] == "pause").mean()), 3),
            "ever_paused": round(len(ever_pause) / n, 3),
            "ever_said_keep": round(len(ever_keep) / n, 3),
            "sample_ratio_flags": int((~g["srm_ok"]).sum()),
        }
    weeks = sorted(records["weeks"].unique())
    for k in (4, 12):
        if k in weeks:
            out[f"lifetime_false_pause_{k}_looks"] = out["by_week"][f"week_{k}"]["ever_paused"]
    old_ever = set()
    for k in weeks:
        old_ever |= set(records.loc[(records["weeks"] == k) & (records["old_rule"] == "pause"), "rest"])
        if k in (4, 12):
            out[f"lifetime_false_pause_{k}_looks_rule_before"] = round(len(old_ever) / max(out["offers"], 1), 3)
    return out


def adaptive_holdout(quotes: list, base: float = 0.10, early: float = 0.30) -> np.ndarray:
    """Holdout share per restaurant for weeks 1-2: larger when the forecast range includes zero
    (the offer's sign is uncertain, so learning fast is worth more customers in the control group)."""
    out = np.full(len(quotes), base)
    for r, q in enumerate(quotes):
        if q is not None and q["profit_low"] < 0 < q["profit_high"]:
            out[r] = early
    return out
