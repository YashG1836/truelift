"""Demo only: simulated weeks for an approved offer, and the itemised payout.

In production the weekly measurement reads Zomato's exposure and order logs. Here a simulated
week writes exactly those two logs (through `Store.log_week`) and the measurement is computed
from them, so the data flow is the real one even though the customers are simulated
(audit TL-028). Competitors keep today's offers; the offer's own decision table decides who is
eligible, which is the same table `serve` reads, so the customers the page labels "control
group" are the ones the measurement holds out (TL-004).
"""

from __future__ import annotations

import copy

import numpy as np
import pandas as pd

from .economics import Terms
from .engine import weekly_message
from .observability import FORECAST_RATIO, HOLDOUT_SHARE
from .sim import display_name

BACKGROUND_OFFER_BASE = 10_000_000  # ids for competitors' offers in the simulated market


def payout_for(orders: pd.DataFrame, terms: Terms) -> dict:
    """The week's payout lines for one restaurant, with the rates beside the amounts."""
    reward = float(orders["reward"].sum())
    commission = float(orders["commission"].sum())
    p = {
        "orders": int(len(orders)),
        "gross_sales": round(float(orders["basket"].sum())),
        "discount_paid_by_you": round(float(orders["restaurant_funded"].sum()) - reward),
        "brand_pack_rewards_paid_by_you": round(reward),
        "discount_paid_by_zomato": round(float(orders["zomato_funded"].sum())),
        "commission": round(commission),
        "commission_rate": terms.commission_rate,
        "gst_on_commission": round(terms.gst_on_commission * commission),
        "gst_rate": terms.gst_on_commission,
    }
    p["net_payout"] = (
        p["gross_sales"]
        - p["discount_paid_by_you"]
        - p["brand_pack_rewards_paid_by_you"]
        - p["commission"]
        - p["gst_on_commission"]
    )
    return p


def week_rows(state, offer, w: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Simulate week `w` of an offer (deterministic). Returns (all of this restaurant's visits,
    the eligible ones with the model's predictions), without logging anything."""
    m, engine = state.market, state.engine
    occ, feats = state.week_inputs(w)
    rid, d = offer.restaurant_id, offer.design
    pol = copy.deepcopy(state.background)
    for attr in ("discount", "min_order", "offpeak_only", "zomato_share", "reward", "audience"):
        getattr(pol, attr)[rid] = getattr(d, attr)
    pol.holdout = engine.holdout
    pol.offer_id = BACKGROUND_OFFER_BASE + np.arange(m.n_rest)
    pol.offer_id[rid] = offer.id
    table = offer.table

    def from_table(fe: dict, policy, mask: np.ndarray) -> np.ndarray:
        return table.eligible(np.asarray(fe["cust"])[mask], np.asarray(fe["slot"])[mask])

    pol.scorer = from_table  # only this restaurant's offer is targeted
    res = m.run_week(occ, pol, feats, salt=0, truth=True)
    mine = res["rest"] == rid
    df = pd.DataFrame({k: v[mine] for k, v in res.items() if isinstance(v, np.ndarray) and len(v) == len(mine)})
    df["visit_id"] = np.flatnonzero(mine)
    el = df[df["eligible"]].reset_index(drop=True)
    v = engine.design_values(el, d, float(m.aov[rid]), state.baskets[rid])
    el["p0"], el["p1"], el["gain"] = v["p0"], v["p1"], v["gain"]
    el["base_profit"] = v["p0"] * v["profit0"]
    return df, el


def simulate_week(state, offer) -> dict:
    """Run the offer's next week of simulated customers; log it; measure it from the log."""
    engine = state.engine
    w = len(offer.weeks) + 1
    rid, d = offer.restaurant_id, offer.design
    aov = float(state.market.aov[rid])
    df, el = week_rows(state, offer, w)
    state.store.log_week(offer.id, w, el, engine.model_version)

    rows = state.store.measurement_rows(offer.id)
    meas = engine.measure(
        rows,
        aov,
        float(rows["gain"].mean()),
        float((rows["p1"] - rows["p0"]).mean()),
        rows["base_profit"].to_numpy(),
        rows["p0"].to_numpy(),
    )
    sh = el["shown"].to_numpy()
    week_truth = {
        "extra_orders": float((el["p"] - el["p_cf"]).to_numpy()[sh].sum()),
        "extra_profit": float((el["p"] * el["profit"] - el["p_cf"] * el["profit_cf"]).to_numpy()[sh].sum()),
    }
    prev = offer.weeks[-1]["simulator_truth"] if offer.weeks else {"extra_orders": 0.0, "extra_profit": 0.0}
    truth = {k: prev[k] + week_truth[k] for k in week_truth}
    t, c, ch = rows["shown"].to_numpy(), rows["holdout"].to_numpy(), rows["chosen"].to_numpy()
    experiment = {
        "shown_visits": int(t.sum()),
        "shown_orders": int((t & ch).sum()),
        "control_visits": int(c.sum()),
        "control_orders": int((c & ch).sum()),
    }
    payout = payout_for(df[df["chosen"]], state.terms)
    name = display_name(state.R.loc[rid])
    week = {
        "week": w,
        "measurement": meas,
        "simulator_truth": truth,
        "payout": payout,
        "experiment": experiment,
        "whatsapp": weekly_message(name, w, meas, d, engine.holdout),
    }

    eligible = experiment["shown_visits"] + experiment["control_visits"]
    if eligible:
        HOLDOUT_SHARE.set(experiment["control_visits"] / eligible)
    measured = meas["profit"]["total"]
    if abs(measured) > 1e-9:
        FORECAST_RATIO.set((offer.quote["profit_change"] * w - measured) / abs(measured))
    return week
