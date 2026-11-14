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

    Windows: "4w" features use the last four recorded weeks; "all" and "weeks since" use every
    recorded week, with weeks since capped at 8 (8 = no order in the window).
    """

    def __init__(self, market, hist):
        po, pv = hist.pair_orders, hist.pair_visits
        n, L = market.n_cust, market.per_loc
        last4 = slice(max(0, len(po) - 4), len(po))
        self.n_weeks = len(po)
        self.n4 = max(1, len(po[last4]))
        self.p4 = _total(po[last4], (n, L))
        self.v4 = _total(pv[last4], (n, L))
        self.p_all = _total(po, (n, L))
        self.weeks_since_r = np.full((n, L), 8.0)
        self.weeks_since_c = np.full(n, 8.0)
        for i, arr in enumerate(po):  # most recent week wins
            ago = len(po) - i
            self.weeks_since_r[arr > 0] = min(ago, 8)
            self.weeks_since_c[hist.cust_orders[i] > 0] = min(ago, 8)
        self.co4 = _total(hist.cust_orders[last4], n)
        self.cd4 = _total(hist.cust_disc_orders[last4], n)
        self.cs4 = _total(hist.cust_sessions[last4], n)
        self.c_all = _total(hist.cust_orders, n)
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
