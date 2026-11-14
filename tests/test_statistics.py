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


@pytest.mark.slow
def test_false_pause_rate_under_null(quick_report):
    """TL-017: placebo offers (true effect zero) are almost never paused over a consent period,
    and far less often than with the rule used before (pause when the 80% range is below zero)."""
    aa = quick_report["main"]["aa_test"]
    assert aa["lifetime_false_pause_4_looks"] <= 0.05
    assert aa["lifetime_false_pause_12_looks"] < aa["lifetime_false_pause_12_looks_rule_before"]


@pytest.mark.slow
def test_weekly_ranges_cover_the_truth_near_the_stated_rate(quick_report):
    """The 80% range covers the true effect close to 80% of the time by the end of the period."""
    m = quick_report["main"]["measurement"]["after_4_weeks"]
    assert 0.7 <= m["coverage_80"] <= 0.95
    assert m["sample_ratio_flags"] <= 2


@pytest.mark.slow
def test_losing_blanket_offers_are_flagged(quick_report):
    """TL-009: within the consent period a good share of truly losing blanket offers is paused or
    flagged as probably losing, and no profitable one is paused by week 4."""
    d = quick_report["main"]["detection"]["blanket_fixed_holdout"]["by_week"]["week_4"]
    assert d["losing_paused_or_warned"] >= 0.2
    assert d["profitable_paused"] <= 0.02
