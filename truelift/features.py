"""Observable features of a (customer, restaurant) menu visit, computed only from order history.

`FeatureSource` is the interface a production system would implement from its own logs (a
nightly feature job or a feature store). `HistoryFeatures` is the in-memory implementation used
by the simulator, the pipeline and the service: it aggregates the history once, after which any
visit's features are array lookups. That turns the serving path from a scan of the whole history
into an index (audit TL-005, TL-013).
"""

from __future__ import annotations

from typing import Protocol

import numpy as np
import pandas as pd

FEATURE_NAMES = (
    "c_orders_pw",
    "c_disc_share",
    "c_weeks_since",
    "c_sessions_pw",
    "c_no_order_8w",
    "cr_orders_4w",
    "cr_orders_all",
    "cr_visits_4w",
    "cr_weeks_since",
    "r_rating",
    "r_aov",
    "r_logvotes",
)
# Not a model input: Zomato knows each account's age, so "new to Zomato" (an account opened in the
# offer's period, no order ever) is observable. Co-funding uses it; the model uses c_no_order_8w,
# which also flags dormant customers and so must not decide who Zomato pays for (audit TL-042).
FUNDING_FEATURES = ("c_new_account",)

# One definition of every window, the same in training, quoting, serving and evaluation (audit TL-007):
RECENT_WEEKS = 4  # "4w" features: orders, visits, sessions and discount use in the last 4 weeks
EVER_WEEKS = 8  # "all" and recency: the last 8 weeks, the history a feature job would keep
NO_ORDER = EVER_WEEKS + 1  # weeks since the last order when there is none in the window


class FeatureSource(Protocol):
    def for_exposures(self, cust: np.ndarray, local: np.ndarray, rest: np.ndarray) -> dict[str, np.ndarray]:
        """Features for many (customer, restaurant) visits at once."""
        ...

    def for_pair(self, cust: int, local: int, rest: int, slot: int, reward: float = 0.0) -> pd.DataFrame:
        """One visit as a one-row frame, ready for the engine."""
        ...


def _total(weeks: list, shape) -> np.ndarray:
    """Element-wise sum of weekly count arrays, as floats; zeros when no week is recorded."""
    out = np.zeros(shape)
    for w in weeks:
        out += w
    return out


class HistoryFeatures:
    """Aggregates of a history snapshot, computed once.

    Only the last EVER_WEEKS recorded weeks are used, whatever the history's length: "4w" features
    use the last RECENT_WEEKS of them; "all" and "weeks since" use all of them, and "weeks since"
    is NO_ORDER when there is no order in the window. So older weeks never change a feature, and a
    model trained on one window is never served another (audit TL-007).
    """

    def __init__(self, market, hist, recent_weeks: int = RECENT_WEEKS, ever_weeks: int = EVER_WEEKS):
        po, pv = hist.pair_orders[-ever_weeks:], hist.pair_visits[-ever_weeks:]
        co, cd = hist.cust_orders[-ever_weeks:], hist.cust_disc_orders[-ever_weeks:]
        cs = hist.cust_sessions[-ever_weeks:]
        n, L = market.n_cust, market.per_loc
        recent = slice(max(0, len(po) - recent_weeks), len(po))
        self.n_weeks = len(po)
        self.n4 = max(1, len(po[recent]))
        self.p4 = _total(po[recent], (n, L))
        self.v4 = _total(pv[recent], (n, L))
        self.p_all = _total(po, (n, L))
        none = float(ever_weeks + 1)
        self.weeks_since_r = np.full((n, L), none)
        self.weeks_since_c = np.full(n, none)
        for i, arr in enumerate(po):  # most recent week wins
            ago = float(len(po) - i)
            self.weeks_since_r[arr > 0] = ago
            self.weeks_since_c[co[i] > 0] = ago
        self.co4 = _total(co[recent], n)
        self.cd4 = _total(cd[recent], n)
        self.cs4 = _total(cs[recent], n)
        self.c_all = _total(co, n)
        self.new_account = market.c_joiner.astype(float)
        self.rating = market.rating
        self.aov = market.aov
        self.logvotes = np.log1p(market.R["votes"].to_numpy(float))

    def for_exposures(self, cust, local, rest) -> dict[str, np.ndarray]:
        cust, local, rest = np.asarray(cust), np.asarray(local), np.asarray(rest)
        return {
            "c_orders_pw": self.co4[cust] / self.n4,
            "c_disc_share": self.cd4[cust] / np.maximum(self.co4[cust], 1),
            "c_weeks_since": self.weeks_since_c[cust],
            "c_sessions_pw": self.cs4[cust] / self.n4,
            "c_no_order_8w": (self.c_all[cust] == 0).astype(float),
            "c_new_account": self.new_account[cust],
            "cr_orders_4w": self.p4[cust, local],
            "cr_orders_all": self.p_all[cust, local],
            "cr_visits_4w": self.v4[cust, local],
            "cr_weeks_since": self.weeks_since_r[cust, local],
            "r_rating": self.rating[rest],
            "r_aov": self.aov[rest],
            "r_logvotes": self.logvotes[rest],
        }

    def for_pair(self, cust: int, local: int, rest: int, slot: int, reward: float = 0.0) -> pd.DataFrame:
        f = self.for_exposures(np.array([cust]), np.array([local]), np.array([rest]))
        f.update(slot=np.array([slot]), reward=np.array([float(reward)]))
        return pd.DataFrame(f)


# Counts and recencies take few values: any value never seen in training is a skew. Rates and
# restaurant attributes are checked against the training range instead.
DISCRETE = ("c_weeks_since", "cr_weeks_since", "cr_orders_4w", "cr_orders_all", "cr_visits_4w", "c_no_order_8w")
SKEW_LIMIT = 0.005  # share of rows outside the training support that fails the check


def skew_report(train: pd.DataFrame, others: dict[str, pd.DataFrame], features=FEATURE_NAMES) -> dict:
    """Training-serving skew: for each feature, the share of rows in each other table (quote input,
    evaluation) whose value the model never saw in training, plus quantiles for the record."""
    out: dict = {"limit": SKEW_LIMIT, "features": {}, "worst_share": 0.0}
    for f in features:
        if f not in train:
            continue
        t = train[f].to_numpy()
        entry = {"train_quantiles": [round(float(q), 4) for q in np.quantile(t, (0.05, 0.5, 0.95))]}
        support = set(np.unique(t).tolist()) if f in DISCRETE else None
        for name, df in others.items():
            v = df[f].to_numpy()
            if support is not None:
                outside = ~np.isin(v, list(support))
            else:
                outside = (v < t.min()) | (v > t.max())
            share = float(outside.mean()) if len(v) else 0.0
            entry[name] = {
                "share_outside": round(share, 5),
                "quantiles": [round(float(q), 4) for q in np.quantile(v, (0.05, 0.5, 0.95))],
            }
            out["worst_share"] = max(out["worst_share"], share)
        out["features"][f] = entry
    out["passed"] = out["worst_share"] <= SKEW_LIMIT
    return out
