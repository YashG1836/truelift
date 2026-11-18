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
from .engine import measure_reward, weekly_message
from .i18n import DRAFTS
from .observability import FORECAST_RATIO, HOLDOUT_SHARE
from .sim import display_name

BACKGROUND_OFFER_BASE = 10_000_000  # ids for competitors' offers in the simulated market
MIN_GROUP_CUSTOMERS = 20  # smallest group whose order counts an owner may see (docs/privacy_and_fairness.md)


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


def week_rows(state, offer, w: int, full_market: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Simulate week `w` of an offer (deterministic). Returns (all of this restaurant's visits,
    the eligible ones with the model's predictions), without logging anything.

    Only the ordering occasions in which this restaurant's menu was opened are simulated: a
    customer's choice on one occasion depends only on the menus of that occasion, so the
    restaurant's rows are exactly those of the full market (`full_market=True`, checked by a test),
    at a small fraction of the work."""
    m, engine = state.market, state.engine
    occ, feats = state.week_inputs(w + offer.week_offset)  # a renewal runs the weeks after the last period
    rid, d = offer.restaurant_id, offer.design
    pol = copy.deepcopy(state.background)
    if pol.pct is None:  # competitors run flat offers; this restaurant's may be a percentage
        pol.pct = np.zeros(m.n_rest)
    for attr in ("discount", "min_order", "offpeak_only", "zomato_share", "reward", "audience", "pct"):
        getattr(pol, attr)[rid] = getattr(d, attr)
    pol.holdout = engine.holdout
    pol.reward_holdout = engine.holdout  # the reward's own control group, same share (TL-016)
    pol.offer_id = BACKGROUND_OFFER_BASE + np.arange(m.n_rest)
    pol.offer_id[rid] = offer.holdout_key
    table = offer.table

    def from_table(fe: dict, policy, mask: np.ndarray) -> np.ndarray:
        return table.eligible(np.asarray(fe["cust"])[mask], np.asarray(fe["slot"])[mask])

    pol.scorer = from_table  # only this restaurant's offer is targeted
    k = occ["rest"].shape[1]
    if full_market:
        keep = np.arange(len(occ["cust"]))
    else:
        keep = np.flatnonzero((occ["rest"] == rid).any(1))
        n_occ = len(occ["cust"])
        occ = {key: v[keep] if isinstance(v, np.ndarray) and len(v) == n_occ else v for key, v in occ.items()}
    visit = (keep[:, None] * k + np.arange(k)).ravel()  # each exposure's index in the full market
    if not full_market:
        feats = {key: np.asarray(v)[visit] for key, v in feats.items()}
    res = m.run_week(occ, pol, feats, salt=0, truth=True)
    res["occ"] = keep[res["occ"]]
    mine = res["rest"] == rid
    df = pd.DataFrame({key: v[mine] for key, v in res.items() if isinstance(v, np.ndarray) and len(v) == len(mine)})
    df["visit_id"] = visit[mine]
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
    regulars = df[df["reward_offered"]] if d.reward > 0 else None
    state.store.log_week(offer.id, w, el, engine.model_version, reward_rows=regulars)

    rows = state.store.measurement_rows(offer.id)
    has_rows = len(rows) > 0  # a narrow design can have no eligible visit yet
    weekly_eligible = float(offer.quote["eligible_visits"])
    meas = engine.measure(
        rows,
        aov,
        float(rows["gain"].mean()) if has_rows else 0.0,
        float((rows["p1"] - rows["p0"]).mean()) if has_rows else 0.0,
        rows["base_profit"].to_numpy(),
        rows["p0"].to_numpy(),
        sigma=engine.sigma_for(d, weekly_eligible, aov),
        planned_shown_visits=weekly_eligible * state.settings.consent_weeks * (1 - engine.holdout),
    )
    sh = el["shown"].to_numpy()
    week_truth = {
        "extra_orders": float((el["p"] - el["p_cf"]).to_numpy()[sh].sum()),
        "extra_profit": float((el["p"] * el["profit"] - el["p_cf"] * el["profit_cf"]).to_numpy()[sh].sum()),
    }
    prev = offer.weeks[-1]["simulator_truth"] if offer.weeks else {"extra_orders": 0.0, "extra_profit": 0.0}
    truth = {k: prev[k] + week_truth[k] for k in week_truth}
    t, c, ch = rows["shown"].to_numpy(), rows["holdout"].to_numpy(), rows["chosen"].to_numpy()
    cust = rows["cust"].to_numpy()
    groups = (len(np.unique(cust[t])), len(np.unique(cust[c])))
    # privacy (audit A13 F4): no order counts for a group of fewer than MIN_GROUP_CUSTOMERS people,
    # so the owner can never read a handful of identifiable customers' behaviour off the table
    hide = min(groups) < MIN_GROUP_CUSTOMERS
    experiment = {
        "shown_visits": int(t.sum()),
        "shown_orders": None if hide else int((t & ch).sum()),
        "control_visits": int(c.sum()),
        "control_orders": None if hide else int((c & ch).sum()),
        "shown_customers": groups[0],
        "control_customers": groups[1],
        "suppressed": hide,
        "min_group_customers": MIN_GROUP_CUSTOMERS,
    }
    payout = payout_for(df[df["chosen"]], state.terms)
    name = display_name(state.R.loc[rid])
    week = {
        "week": w,
        "measurement": meas,
        "simulator_truth": truth,
        "payout": payout,
        "experiment": experiment,
    }
    if d.reward > 0:
        week["brand_pack"] = measure_reward(state.store.reward_rows(offer.id))
    week["whatsapp"] = weekly_message(name, w, meas, d, engine.holdout, week.get("brand_pack"))
    # draft translations, shown only when switched on (decision D4; truelift/i18n.py)
    week["whatsapp_i18n"] = {
        lang: weekly_message(name, w, meas, d, engine.holdout, week.get("brand_pack"), lang) for lang in DRAFTS
    }

    eligible = experiment["shown_visits"] + experiment["control_visits"]
    if eligible:
        HOLDOUT_SHARE.set(experiment["control_visits"] / eligible)
    measured = meas["profit"]["total"]
    if abs(measured) > 1e-9:
        FORECAST_RATIO.set((offer.quote["profit_change"] * w - measured) / abs(measured))
    return week
