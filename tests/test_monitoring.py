"""Monitoring (audit A16 O4, O7): the drift report and the weekly guardrails."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from truelift.features import HistoryFeatures
from truelift.monitoring import PSI_FAIL, PSI_WATCH, drift_report, guardrails, psi
from truelift.sim import Config, Market, build_history


@pytest.fixture(scope="module")
def small(restaurants):
    market = Market(restaurants, Config(customers_per_locality=300))
    hist, rows = build_history(market)
    return market, hist, rows


def test_psi_is_zero_for_the_same_distribution_and_large_for_a_shift():
    rng = np.random.default_rng(0)
    a, b = rng.normal(0, 1, 20000), rng.normal(0, 1, 20000)
    assert psi(a, b, discrete=False) < 0.01
    assert psi(a, rng.normal(1.0, 1, 20000), discrete=False) > PSI_FAIL
    counts = rng.poisson(1.0, 20000)
    assert psi(counts, rng.poisson(1.0, 20000), discrete=True) < 0.01
    assert psi(counts, rng.poisson(2.0, 20000), discrete=True) > PSI_FAIL


def test_drift_report_passes_on_the_pipeline_windows(small):
    market, hist, rows = small
    occ = market.occasions(1)
    ev = pd.DataFrame(market.flat_features(hist, occ))
    rep = drift_report(rows, {"evaluation": ev})
    assert rep["passed"], {f: e["evaluation"]["psi"] for f, e in rep["features"].items()}
    assert rep["worst_psi"] <= PSI_FAIL


def test_drift_report_fails_when_the_old_window_fault_returns(small):
    """TL-007: serving once counted "last 4 weeks" features over the whole history. Recreate that
    (an 8-week window under the 4-week names) and the report must fail."""
    market, hist, rows = small
    occ = market.occasions(1)
    k = occ["rest"].shape[1]
    cust, local, rest = np.repeat(occ["cust"], k), occ["local"].ravel(), occ["rest"].ravel()
    wrong = pd.DataFrame(HistoryFeatures(market, hist, recent_weeks=8).for_exposures(cust, local, rest))
    rep = drift_report(rows, {"evaluation": wrong})
    assert not rep["passed"]
    recent = ("c_orders_pw", "c_sessions_pw", "cr_orders_4w", "cr_visits_4w")  # the "last 4 weeks" inputs
    assert any(rep["features"][f]["evaluation"]["status"] == "fail" for f in recent)


def test_guardrails_flag_a_broken_split_and_a_bad_forecast():
    rest = np.arange(200)
    good = pd.DataFrame(
        {
            "rest": rest,
            "weeks": 4,
            "est_profit": np.full(200, 400.0),
            "w_own": np.full(200, 0.5),
            "verdict": ["keep"] * 180 + ["wait"] * 20,
            "srm_ok": True,
        }
    )
    fc = {int(r): 100.0 for r in rest}
    g = guardrails(good, fc)
    assert g["passed"] and g["offers"] == 200
    bad = good.assign(srm_ok=[False] * 3 + [True] * 197)
    checks = {c["check"]: c for c in guardrails(bad, {int(r): 300.0 for r in rest})["checks"]}
    assert not checks["sample_ratio"]["passed"] and not checks["forecast_against_measured"]["passed"]
    assert all(c["meaning"] and c["threshold"] for c in checks.values())
    assert PSI_WATCH < PSI_FAIL
