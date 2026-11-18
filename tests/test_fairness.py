"""Fairness guards (audit A13): what the model may read, and who receives the savings."""

from __future__ import annotations

import pytest

from truelift.model import ALLOWED_FEATURES, BASE_FEATURES, DESIGN_FEATURES, PROTECTED_WORDS


def test_every_model_input_is_on_the_allow_list():
    used = set(BASE_FEATURES) | set(DESIGN_FEATURES)
    assert used <= set(ALLOWED_FEATURES), f"inputs without an allow-list entry: {sorted(used - set(ALLOWED_FEATURES))}"


def test_allow_list_names_no_protected_trait_or_home_location():
    for name, meaning in ALLOWED_FEATURES.items():
        assert not set(name.split("_")) & PROTECTED_WORDS, name
        assert meaning.strip(), f"{name} has no description"


def test_fitted_model_reads_only_allowed_columns(small_trained):
    """The fitted trees themselves, not just the constants: what the model was given to learn from."""
    m = small_trained.model
    for est in (m.m0, m.m1):
        assert set(est.feature_names_in_) <= set(ALLOWED_FEATURES)


@pytest.mark.slow
def test_fairness_report_names_the_loyalty_gap_and_prices_the_mitigations(quick_report):
    """TrueLift offers regulars fewer savings than blanket offers (they order anyway); making
    regulars always eligible closes that gap, at a cost the report states."""
    f = quick_report["main"]["fairness"]
    assert f["today_blanket"]["loyalty_gap"] <= 0.01
    assert f["truelift"]["loyalty_gap"] > f["today_blanket"]["loyalty_gap"]
    assert f["regulars_always_eligible"]["loyalty_gap"] < f["truelift"]["loyalty_gap"]
    for k in ("brand_pack_for_regulars", "regulars_always_eligible", "random_20pct_also_shown"):
        assert isinstance(f["mitigations"][k]["own_offer_profit_change_vs_truelift"], int)
    segs = f["truelift"]["by_segment"]
    assert set(segs) == {"customer_type", "locality", "price_band", "regular", "new_account"}
