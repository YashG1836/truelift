"""Market-level results on the quick configuration (slow): what the pipeline claims for Zomato.

Each test checks a property the write-up states, against the simulator's truth.
"""

from __future__ import annotations

import pytest


@pytest.mark.slow
def test_owners_who_decline_blind_cost_zomato_commission(quick_report):
    """WP-13: under OTP consent, the more owners stop approving blanket offers they cannot judge,
    the less commission Zomato earns; owners who decline only losing offers cost it nothing."""
    a = quick_report["main"]["consent_attrition"]
    blind = a["blanket_owners_decline_blind"]
    comm = [blind[k]["zomato_commission_change"] for k in ("10%", "20%", "30%", "50%")]
    assert comm == sorted(comm, reverse=True)
    blanket = quick_report["main"]["policies"]["today_blanket"]
    assert comm[0] < blanket["zomato_commission_change"]
    assert a["blanket_losing_owners_decline"]["offers_that_lose"] == 0
    assert a["blanket_losing_owners_decline"]["zomato_commission_change"] >= blanket["zomato_commission_change"]
    share = a["break_even_blind_decline_share"]
    assert share is None or 0.0 <= share <= 0.5


@pytest.mark.slow
def test_unmeasured_cofunding_moves_money_without_creating_orders(quick_report):
    """TL-010: the customer sees the same offer whoever pays, so co-funding that changes no offer
    is a transfer from Zomato to restaurants, rupee for rupee."""
    m = quick_report["main"]
    led = m["zomato_ledger"]["cofunding"]
    tl, cf = m["policies"]["truelift"], m["policies"]["zomato_cofund_naive"]
    assert led["pure_transfer"] == (led["extra_platform_incremental_orders"] <= 0)
    if led["pure_transfer"]:
        gain = cf["restaurant_profit_change"] - tl["restaurant_profit_change"]
        assert gain == pytest.approx(
            led["extra_zomato_funded_discount"], abs=0.01 * led["extra_zomato_funded_discount"]
        )
    shares = m["zomato_ledger"]["platform_incremental_share_of_extra_orders"]
    assert all(0.0 < v < 1.0 for v in shares.values())


@pytest.mark.slow
def test_early_adopters_gain_and_the_market_still_grows(quick_report):
    """A06 S4: with a tenth or three tenths of restaurants on TrueLift and the rest on today's
    offers, adopters gain more than the others lose, and Zomato's commission rises."""
    for k in ("10%", "30%"):
        p = quick_report["main"]["partial_adoption"][k]
        assert p["adopters_profit_change_a_week"] > 0
        assert p["adopters_profit_change_a_week"] + p["others_profit_change_a_week"] > 0
        assert p["zomato_commission_change_a_week"] > 0


@pytest.mark.slow
def test_frontier_and_control_set_are_reported(quick_report):
    m = quick_report["main"]
    pts = m["zomato_weight_frontier"]["points"]
    assert [p["zomato_weight"] for p in pts] == [0.0, 0.5, 1.0, 2.0]
    assert pts[0]["restaurant_profit_change"] == m["policies"]["truelift"]["restaurant_profit_change"]
    cs = m["control_set"]
    assert (
        cs["holdout_only"]["qini"] > 0 and cs["holdout_only"]["control_rows"] < cs["all_unshown_in_use"]["control_rows"]
    )
    mh = m["moving_history"]
    fixed, moving = mh["fixed_snapshot"], mh["features_follow_each_week"]
    assert moving["own_offer_profit_effect"] == pytest.approx(fixed["own_offer_profit_effect"], rel=0.05)
