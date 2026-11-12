"""Uplift model: how likely a customer is to order from a restaurant with and without an offer.

T-learner (two models):
  m0(x)          = P(order | customer and restaurant features, no offer shown)
  m1(x, design)  = P(order | same features, offer with this design shown)
  uplift         = m1 - m0   (extra orders the offer creates for this customer visit)
Training data must come from random assignment (the 10% holdout), so m1 - m0 is causal.
Gradient-boosted trees from scikit-learn; no special libraries needed.

Also here: the Qini curve, the standard check of whether an uplift ranking finds the customers
a discount actually moves (higher than a random ranking = better).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

BASE_FEATURES = [
    "c_orders_pw", "c_disc_share", "c_weeks_since", "c_sessions_pw", "c_new_to_zomato",
    "cr_orders_4w", "cr_orders_all", "cr_visits_4w", "cr_weeks_since",
    "r_rating", "r_aov", "r_logvotes", "slot", "reward",
]
DESIGN_FEATURES = ["offer_discount", "disc_pct", "mov_ratio"]


def design_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["offer_discount"] = df["offer_discount"].astype(float)
    out["disc_pct"] = out["offer_discount"] / df["r_aov"]
    out["mov_ratio"] = np.where(df["min_order"] > 0, df["min_order"] / df["r_aov"], 0.0)
    return out


def _gbm(seed: int) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, max_leaf_nodes=31,
                                          min_samples_leaf=200, l2_regularization=1.0,
                                          early_stopping=True, validation_fraction=0.1,
                                          random_state=seed)


@dataclass
class UpliftModel:
    m0: HistGradientBoostingClassifier
    m1: HistGradientBoostingClassifier

    @classmethod
    def fit(cls, rows: pd.DataFrame, seed: int = 0) -> "UpliftModel":
        """rows: exposures from a period with random holdouts. Needs columns BASE_FEATURES,
        offer_discount, min_order, shown, chosen."""
        ctrl = rows[~rows["shown"]]
        trt = rows[rows["shown"]]
        m0 = _gbm(seed).fit(ctrl[BASE_FEATURES], ctrl["chosen"])
        x1 = pd.concat([trt[BASE_FEATURES], design_columns(trt)], axis=1)
        m1 = _gbm(seed + 1).fit(x1, trt["chosen"])
        return cls(m0, m1)

    def p0(self, x: pd.DataFrame) -> np.ndarray:
        return self.m0.predict_proba(x[BASE_FEATURES])[:, 1]

    def p1(self, x: pd.DataFrame, discount, min_order) -> np.ndarray:
        d = pd.DataFrame({"offer_discount": discount, "min_order": min_order, "r_aov": x["r_aov"]},
                         index=x.index)
        return self.m1.predict_proba(pd.concat([x[BASE_FEATURES], design_columns(d)], axis=1))[:, 1]


def qini_curve(score: np.ndarray, treated: np.ndarray, y: np.ndarray, points: int = 50):
    """Qini curve: extra outcomes gained by treating the top-k% by score, versus k.

    Returns (fraction treated, cumulative incremental outcomes, random-ranking line).
    """
    order = np.argsort(-score, kind="stable")
    t, yy = treated[order].astype(float), y[order].astype(float)
    nt, nc = np.cumsum(t), np.cumsum(1 - t)
    yt, yc = np.cumsum(yy * t), np.cumsum(yy * (1 - t))
    q = yt - yc * np.divide(nt, nc, out=np.zeros_like(nt), where=nc > 0)
    idx = np.linspace(0, len(q) - 1, points).astype(int)
    frac = (idx + 1) / len(q)
    return frac, q[idx], frac * q[-1]


def qini_coefficient(score, treated, y) -> float:
    """Area between the Qini curve and the random line, divided by the total gain.

    0 means no better than random; higher is better.
    """
    frac, q, rand = qini_curve(score, treated, y, points=200)
    total = q[-1] if q[-1] != 0 else 1.0
    return float(np.trapezoid(q - rand, frac) / abs(total))
