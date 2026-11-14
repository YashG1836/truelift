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

from .engine import Design, Engine, effect_and_se, expected_variance, fit_topup_value
from .model import UpliftModel
from .sim import History, Market, build_history, restaurant_baskets


def shadow_offers(rows: pd.DataFrame, engine: Engine, baskets, aov) -> pd.DataFrame:
    """One row per shadow-phase offer (restaurant-week): own holdout estimate and model prior."""
    out = []
    el = rows[rows["eligible"]]
    for (r, w), g in el.groupby(["rest", "week"]):
        t, c = g["shown"].to_numpy(), g["holdout"].to_numpy()
        cust = g["cust"].to_numpy()
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
        noise_o = v["p0"] * (1 - v["p0"])
        noise_p = noise_o * v["profit0"] ** 2
        # the whole offer, the visits a targeted version would show and those it would skip
        # (selection is on features only, so shown vs held-out stays random inside each)
        subsets = (("all", np.ones(len(g), bool)), ("targeted", v["gain"] > 0), ("excluded", v["gain"] <= 0))
        for subset, keep in subsets:
            tt, cc = t & keep, c & keep
            if tt.sum() < 20 or cc.sum() < 5:
                continue

            # the same estimator and noise as the weekly measurement (customer-level, audit TL-029)
            # every offer counts here, however few orders it has (its noise averages out across
            # offers); two random halves of its customers give the material for split-half noise
            # the weekly measurement's own estimator: regression-adjusted by each visit's
            # predicted no-offer outcome, in the engine's adjustment mode
            base_p, base_o, how = v["p0"] * v["profit0"], v["p0"], engine.adjust
            own_p, _ = effect_and_se(yp, tt, cc, cust, base_p, adjust=how, min_events=0)
            own_o, _ = effect_and_se(yo, tt, cc, cust, base_o, adjust=how, min_events=0)
            half = (cust % 2) == 0
            halves = [
                (
                    effect_and_se(yp, tt & h, cc & h, cust, base_p, adjust=how, min_events=0)[0],
                    effect_and_se(yo, tt & h, cc & h, cust, base_o, adjust=how, min_events=0)[0],
                )
                for h in (half, ~half)
            ]
            ev_p, ev_o = expected_variance(noise_p, tt, cc), expected_variance(noise_o, tt, cc)
            if not (math.isfinite(ev_p) and math.isfinite(ev_o)):
                continue
            scale = engine.noise_scale or (1.0, 1.0)
            se_p, se_o = math.sqrt(scale[0] * ev_p), math.sqrt(scale[1] * ev_o)
            out.append(
                {
                    "rest": r,
                    "week": w,
                    "aov": aov[r],
                    "subset": subset,
                    "visits": int(tt.sum()),
                    "control_visits": int(cc.sum()),
                    "own_profit": own_p,
                    "se_profit": se_p,
                    "prior_profit": float(v["gain"][keep].mean()),
                    "own_orders": own_o,
                    "se_orders": se_o,
                    "expected_var_profit": ev_p,
                    "expected_var_orders": ev_o,
                    "half_diff_profit": halves[0][0] - halves[1][0],
                    "half_diff_orders": halves[0][1] - halves[1][1],
                    "prior_orders": float((v["p1"] - v["p0"])[keep].mean()),
                }
            )
    return pd.DataFrame(out)


def noise_scale(offers: pd.DataFrame) -> tuple[float, float]:
    """How much real noise an offer's estimate has, per unit of the model's expected variance.

    Each shadow offer's customers are split into two random halves (by customer, so one customer's
    visits stay together) and the effect is estimated in each. The two halves differ only by noise,
    so the squared difference over four estimates the variance of the full estimate, clustering of
    a customer's visits included, without trusting any one offer's tiny control group. Summed over
    offers and divided by the model's expected variance, it gives one factor per outcome.
    """
    g = offers[offers["subset"] == "all"]
    out = []
    for diff, ev in (("half_diff_profit", "expected_var_profit"), ("half_diff_orders", "expected_var_orders")):
        ok = np.isfinite(g[diff]) & np.isfinite(g[ev]) & (g[ev] > 0)
        real = float((g.loc[ok, diff] ** 2).sum() / 4)
        model = float(g.loc[ok, ev].sum())
        out.append(real / model if model > 0 and ok.sum() >= 20 else 1.0)
    return out[0], out[1]


def gain_calibration(offers: pd.DataFrame) -> tuple[float, float]:
    """Scale factors for predicted gains above and below zero, learned from the shadow phase.

    Each shadow offer's control group measures its true effect, separately for the visits the
    model expects to gain (a targeted version shows those) and the visits it expects to lose
    (skipped). Predictions come from a model that never saw that restaurant. The ratio of measured
    to predicted, summed over offers, says how far each side of the predictions should be scaled.
    Visits the model ranks most negative tend to lose less than predicted (regression to the
    mean), which made blanket forecasts too low and overstated what targeting adds (audit TL-006,
    TL-018). The sign of a prediction, and so every targeting decision, is unchanged.
    """
    out = []
    for subset in ("targeted", "excluded"):
        g = offers[offers["subset"] == subset]
        prior = float((g["visits"] * g["prior_profit"]).sum())
        own = float((g["visits"] * g["own_profit"]).sum())
        ratio = own / prior if len(g) >= 20 and abs(prior) > 1e-9 else 1.0
        out.append(float(np.clip(ratio, 0.2, 2.0)))
    return out[0], out[1]


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
            "gain_scale": list(e.gain_scale),
            "noise_scale": list(e.noise_scale) if e.noise_scale else None,
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
    fold_models = [UpliftModel.fit(rows[fold != f], seed=f) for f in (0, 1)]

    def checks(scale: tuple[float, float], noise: tuple[float, float] | None) -> pd.DataFrame:
        parts = []
        for f in (0, 1):
            e = Engine(fold_models[f], topup_value=topup)
            e.gain_scale, e.noise_scale = scale, noise
            parts.append(shadow_offers(rows[fold == f], e, baskets, aov))
        return pd.concat(parts, ignore_index=True)

    first = checks((1.0, 1.0), None)
    scale, noise = gain_calibration(first), noise_scale(first)
    log(f"predicted gains scaled by {scale[0]:.2f} above zero and {scale[1]:.2f} below (shadow-phase holdouts)")
    log(f"real noise of an offer's estimate: {noise[0]:.2f} (profit) and {noise[1]:.2f} (orders) x the model's")
    offers = checks(scale, noise)  # the error left after that calibration sets the ranges
    engine = Engine(model, topup_value=topup)
    engine.gain_scale, engine.noise_scale = scale, noise
    sig = engine.calibrate(offers[offers["subset"] != "excluded"])
    log(
        f"model trained; calibrated error: profit {sig[0]:.4f} x AOV per visit, orders {sig[1]:.4f} per visit "
        f"({len(offers)} shadow-offer checks)"
    )
    return Trained(market, hist, rows, baskets, model, engine, offers, topup_range)
