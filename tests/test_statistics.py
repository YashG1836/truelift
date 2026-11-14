"""Statistical properties of the method on the quick configuration (slow: about a minute each).

Each check is a property the method promises, verified against the simulator's truth.
"""

from __future__ import annotations

import pytest

from truelift.economics import Terms
from truelift.sim import Config, Market


@pytest.fixture(scope="module")
def quick_trained(restaurants):
    from truelift.training import train

    return train(Market(restaurants, Config(customers_per_locality=2000), Terms()))


@pytest.mark.slow
def test_topup_value_recovers_truth(quick_trained):
    """TL-020: the learned top-up value is within 0.05 of the simulator's hidden value."""
    truth = quick_trained.market.cfg.topup_value
    assert abs(quick_trained.engine.topup_value - truth) <= 0.05 + 1e-9
    lo, hi = quick_trained.topup_range
    assert lo - 0.025 <= truth <= hi + 0.025  # inside the 80% interval, up to one grid step


@pytest.mark.slow
def test_forecast_is_centred_on_the_truth_in_todays_market(quick_report):
    """TL-006: the quote an owner approves is close to the true weekly gain, in the market it was
    made for (a tenth of restaurants switch at a time), with misses not all on one side."""
    f = quick_report["main"]["forecast"]["truelift_design_in_todays_market"]
    assert 0.8 <= f["ratio_forecast_to_truth"] <= 1.2
    assert f["coverage_80"] >= 0.8
    assert 0.25 <= f["share_forecast_below_truth"] <= 0.75


@pytest.mark.slow
def test_no_training_serving_skew(quick_report):
    assert quick_report["main"]["skew_check"]["passed"]


@pytest.mark.slow
def test_chosen_version_usually_beats_the_owners_and_its_advantage_is_not_inflated(quick_report):
    """TL-018: the version TrueLift picks truly beats the owner's offer most of the time, and the
    advantage it states is not the flattering best-of-34 number (within a factor of two of the truth)."""
    s = quick_report["main"]["selection"]
    assert s["share_truly_better_than_owner"] >= 0.7
    assert 0.5 <= s["forecast_advantage_total"] / s["true_advantage_total"] <= 2.0
