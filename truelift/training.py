"""Training: simulated history -> uplift model -> calibrated error sizes -> a model bundle.

Shared by the evaluation pipeline (`scripts/run_pipeline.py`) and the test suite's model fixture,
so the service and the tests always load a bundle built by the same code.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .engine import Design, Engine, fit_topup_value
from .model import UpliftModel
from .sim import History, Market, build_history, restaurant_baskets


def shadow_offers(rows: pd.DataFrame, engine: Engine, baskets, aov) -> pd.DataFrame:
    """One row per shadow-phase offer (restaurant-week): own holdout estimate and model prior."""
    out = []
    el = rows[rows["eligible"]]
    for (r, w), g in el.groupby(["rest", "week"]):
        t, c = g["shown"].to_numpy(), g["holdout"].to_numpy()
        if t.sum() < 20 or c.sum() < 5:
            continue
        d = Design(
            float(g["offer_discount"].iloc[0]),
            float(g["min_order"].iloc[0]),
            str(g["audience"].iloc[0]),
            bool(g["offpeak_only"].iloc[0]),
            float(g["offer_reward"].iloc[0]),
        )
        v = engine.design_values(g, d, aov[r], baskets[r])
        yp = g["chosen"].to_numpy() * g["profit"].to_numpy()
        yo = g["chosen"].to_numpy().astype(float)
        # the whole offer, and the subset a targeted version would show (selection is on features
        # only, so shown vs held-out stays random inside it); targeted offers are where errors grow
        for subset, keep in (("all", np.ones(len(g), bool)), ("targeted", v["gain"] > 0)):
            tt, cc = t & keep, c & keep
            if tt.sum() < 20 or cc.sum() < 5:
                continue

            def se(y, tt=tt, cc=cc):
                return math.sqrt(y[tt].var(ddof=1) / tt.sum() + y[cc].var(ddof=1) / cc.sum())

            out.append(
                {
                    "rest": r,
                    "week": w,
                    "aov": aov[r],
                    "subset": subset,
                    "own_profit": yp[tt].mean() - yp[cc].mean(),
                    "se_profit": se(yp),
                    "prior_profit": float(v["gain"][keep].mean()),
                    "own_orders": yo[tt].mean() - yo[cc].mean(),
                    "se_orders": se(yo),
                    "prior_orders": float((v["p1"] - v["p0"])[keep].mean()),
                }
            )
    return pd.DataFrame(out)


def minimum_order_offers(train: pd.DataFrame, model: UpliftModel) -> pd.DataFrame:
    """Past minimum-order offers, one row per restaurant-week: shown visits, the orders among them
    that did not use the offer, and the orders those visits would have made with no offer (from
    the no-offer model, which never saw shown visits)."""
    sh = train[train["shown"] & (train["min_order"] > 0) & (train["offer_reward"] == 0)]
    if not len(sh):
        cols = ["rest", "week", "discount", "min_order", "visits", "skip_orders", "expected_orders"]
        return pd.DataFrame(columns=cols)
    sh = sh.assign(skip=sh["chosen"] & ~sh["takes"], p0=model.p0(sh))
    g = (
        sh.groupby(["rest", "week"])
        .agg(
            discount=("offer_discount", "first"),
            min_order=("min_order", "first"),
            visits=("skip", "size"),
            skip_orders=("skip", "sum"),
            expected_orders=("p0", "sum"),
        )
        .reset_index()
    )
    return g[g["visits"] >= 20]


@dataclass
class Trained:
    """Everything training produces; the pipeline evaluates with it and the service loads its bundle."""

    market: Market
    hist: History
    train: pd.DataFrame
    baskets: list
    model: UpliftModel
    engine: Engine
    offers: pd.DataFrame  # cross-fitted shadow-offer checks used for calibration
    topup_range: tuple = (0.5, 0.5)  # 80% bootstrap interval of the learned top-up value

    def bundle(
        self,
        demo_restaurant: int,
        designs: list[Design] | None = None,
        version: str = "dev",
        metrics: dict | None = None,
        data_sha256: str = "",
    ) -> dict:
        """The model bundle the service loads (`data/processed/model.pkl`), with a record of what
        built it: version, time, library versions, features, metrics (audit A16 O6)."""
        import time
        from dataclasses import asdict

        from .model import BASE_FEATURES, DESIGN_FEATURES, library_versions

        e = self.engine
        return {
            "format": 2,
            "model": self.model,
            "sigma_rel": e.sigma_rel,
            "sigma_orders": e.sigma_orders,
            "topup_value": e.topup_value,
            "config": asdict(self.market.cfg),
            "terms": asdict(self.market.terms),
            "demo_restaurant": int(demo_restaurant),
            "truelift_designs": [asdict(d) for d in (designs or [])],
            "version": version,
            "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "library_versions": library_versions(),
            "features": BASE_FEATURES + DESIGN_FEATURES,
            "training_rows": int(len(self.train)),
            "shadow_offer_checks": int(len(self.offers)),
            "data_sha256": data_sha256,
            "metrics": metrics or {},
        }


def train(market: Market, log: Callable[[str], None] = lambda m: None) -> Trained:
    """Simulate history, learn the top-up value, fit the uplift model, calibrate its error."""
    n = market.n_rest
    aov = market.aov
    hist, rows = build_history(market)
    log(f"history: {len(rows):,} shadow-phase visits, {int(rows['chosen'].sum()):,} orders")
    baskets = restaurant_baskets(rows, n)
    model = UpliftModel.fit(rows, seed=7)
    topup, topup_range = fit_topup_value(minimum_order_offers(rows, model), baskets)
    lo, hi = topup_range
    log(f"learned top-up value from past minimum-order offers: {topup:.3f} (80% interval {lo:.3f}-{hi:.3f})")
    # cross-fitted calibration of model error: each restaurant's error is measured by a model
    # that never saw that restaurant
    fold = rows["rest"] % 2
    priors = []
    for f in (0, 1):
        m_f = UpliftModel.fit(rows[fold != f], seed=f)
        priors.append(shadow_offers(rows[fold == f], Engine(m_f, topup_value=topup), baskets, aov))
    offers = pd.concat(priors, ignore_index=True)
    engine = Engine(model, topup_value=topup)
    sig = engine.calibrate(offers)
    log(
        f"model trained; calibrated error: profit {sig[0]:.4f} x AOV per visit, orders {sig[1]:.4f} per visit "
        f"({len(offers)} shadow-offer checks)"
    )
    return Trained(market, hist, rows, baskets, model, engine, offers, topup_range)
