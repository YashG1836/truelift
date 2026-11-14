"""The simulated market: its truth is consistent, its assumptions are checked, its fast path is
identical to its full path."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from truelift.assignment import in_control_group, stable_uniform
from truelift.sim import Config, History, Market, Policy, build_history, restaurant_baskets


@pytest.fixture(scope="module")
def market(restaurants):
    return Market(restaurants, Config(customers_per_locality=300))


def _week(market, policy):
    occ = market.occasions(1)
    return market.run_week(occ, policy, market.flat_features(History(), occ), salt=5)


def test_no_offer_has_no_effect(market):
    res = _week(market, Policy.none(market.n_rest))
    assert np.allclose(res["p"], res["p_cf"])
    assert np.allclose(res["platform_lift"], 0)


def test_probabilities_are_valid(market):
    n = market.n_rest
    pol = Policy(
        np.full(n, 60.0),
        np.zeros(n),
        np.zeros(n, bool),
        np.zeros(n),
        np.zeros(n),
        np.array(["all"] * n, dtype=object),
        0.10,
    )
    res = _week(market, pol)
    k = market.cfg.menus_per_occasion
    per_occ = res["p"].reshape(-1, k).sum(1) + res["p_swiggy"][::k] + res["p_none"][::k]
    assert np.allclose(per_occ, 1.0)
    assert (res["p"] >= res["p_cf"] - 1e-12)[res["shown"]].all()  # a discount never lowers the chance
    share = res["holdout"].sum() / res["eligible"].sum()
    assert 0.08 < share < 0.12


def test_holdout_hash_is_stable_and_uniform():
    a = np.arange(100000)
    u1 = stable_uniform(a, a % 300, 7)
    assert np.array_equal(u1, stable_uniform(a, a % 300, 7))
    assert abs(u1.mean() - 0.5) < 0.01


def test_control_group_share_and_independence():
    c = np.arange(200000)
    a = in_control_group(c, 11, 0.10)
    b = in_control_group(c, 12, 0.10)
    assert 0.095 < a.mean() < 0.105
    assert abs(np.corrcoef(a, b)[0, 1]) < 0.01  # a different offer is a fresh draw


def test_offer_ids_switch_the_simulator_to_the_shared_assignment(market):
    """With offer ids, the week holds out exactly the customers `in_control_group` names (TL-004)."""
    n = market.n_rest
    pol = Policy(
        np.full(n, 60.0),
        np.zeros(n),
        np.zeros(n, bool),
        np.zeros(n),
        np.zeros(n),
        np.array(["all"] * n, dtype=object),
        0.10,
        offer_id=np.arange(n) + 500,
    )
    res = _week(market, pol)
    el = res["eligible"]
    expected = in_control_group(res["cust"][el], (np.arange(n) + 500)[res["rest"][el]], 0.10)
    assert np.array_equal(res["holdout"][el], expected)


def test_market_rejects_unbalanced_localities(restaurants):
    bad = restaurants[
        ~((restaurants["locality"] == restaurants["locality"].iloc[0]) & (restaurants.index % 50 == 0))
    ].copy()
    bad["restaurant_id"] = np.arange(len(bad))
    with pytest.raises(ValueError, match="same number of restaurants"):
        Market(bad, Config(customers_per_locality=50))


def test_market_rejects_gaps_in_restaurant_ids(restaurants):
    bad = restaurants.copy()
    bad.loc[bad.index[-1], "restaurant_id"] = 10_000
    with pytest.raises(ValueError, match="no gaps"):
        Market(bad, Config(customers_per_locality=50))


def test_light_history_is_identical_to_the_full_one(restaurants):
    """The service's fast path (no training table) must build exactly the same history."""
    cfg = Config(customers_per_locality=120)
    h_full, rows = build_history(Market(restaurants, cfg))
    h_light, light = build_history(Market(restaurants, cfg), light=True)
    for a, b in zip(h_full.pair_orders + h_full.cust_orders, h_light.pair_orders + h_light.cust_orders, strict=True):
        assert np.array_equal(a, b)
    full_b = restaurant_baskets(rows, len(restaurants))
    light_b = restaurant_baskets(light, len(restaurants))
    assert all(np.array_equal(a, b) for a, b in zip(full_b, light_b, strict=True))


def test_features_depend_only_on_history(market):
    occ = market.occasions(2)
    f1 = market.flat_features(History(), occ)
    f2 = market.flat_features(History(), occ)
    assert all(np.array_equal(f1[k], f2[k]) for k in f1)
    assert isinstance(pd.DataFrame(f1), pd.DataFrame)


def _cofund_policy(n):
    return Policy(
        np.full(n, 60.0),
        np.zeros(n),
        np.zeros(n, bool),
        np.full(n, 0.5),
        np.zeros(n),
        np.array(["all"] * n, dtype=object),
        0.10,
    )


def test_cofunding_only_for_new_to_zomato(market):
    """TL-003: Zomato's half of the discount goes only to customers new to Zomato (new accounts)."""
    res = _week(market, _cofund_policy(market.n_rest))
    new = res["c_new_account"] == 1
    assert (res["zomato_funded"][~new] == 0).all()
    assert (res["zomato_funded"][new & res["takes"]] == 30.0).all()
    assert (new & res["takes"]).any()


def test_engine_and_simulator_agree_on_funding(market):
    """The engine's expected Zomato-funded amount per order equals what the simulator pays."""
    from truelift.engine import Engine

    class _Flat:
        def p0(self, x):
            return np.full(len(x), 0.1)

        def p1(self, x, discount, min_order):
            return np.full(len(x), 0.2)

    res = _week(market, _cofund_policy(market.n_rest))
    took = res["takes"]
    x = pd.DataFrame({k: res[k][took] for k in ("c_new_account", "cr_orders_4w", "slot")})
    v = Engine(_Flat()).row_values(x, 60.0, 0.0, 0.0, 0.5, (1.0, 400.0, 400.0, 400.0))
    assert np.allclose(v["zfund1"], res["zomato_funded"][took])


def test_new_to_zomato_matches_first_order(market):
    """TL-042: the funding flag marks accounts with no order ever, not dormant customers."""
    feats = market.flat_features(History(), market.occasions(1))
    k = market.cfg.menus_per_occasion
    cust = np.repeat(market.occasions(1)["cust"], k)
    assert np.array_equal(feats["c_new_account"] == 1, market.c_joiner[cust])
