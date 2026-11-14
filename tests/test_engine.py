"""The engine's decisions with a model whose answers are known in advance."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from truelift.economics import order_money
from truelift.engine import Design, Engine, _cached, design_options, offer_mix, rule_eligible, weekly_message


class _FlatModel:
    """Stand-in model: 10% order chance without an offer, 15% with one."""
    def p0(self, x):
        return np.full(len(x), 0.10)

    def p1(self, x, discount, min_order):
        return np.full(len(x), 0.15)


class _BrokenModel(_FlatModel):
    def p1(self, x, discount, min_order):
        raise RuntimeError("model unavailable")


def _x(n):
    return pd.DataFrame({"slot": np.full(n, 2), "cr_orders_all": np.r_[np.zeros(n // 2), np.ones(n - n // 2)],
                         "cr_weeks_since": np.full(n, 6.0), "cr_orders_4w": np.zeros(n),
                         "c_new_to_zomato": np.zeros(n), "reward": np.zeros(n)})


def test_audience_rules():
    x = _x(10)
    assert rule_eligible(x, Design(60, audience="new_to_restaurant")).sum() == 5
    assert rule_eligible(x, Design(60, audience="lapsed")).sum() == 5
    assert rule_eligible(x, Design(60, offpeak_only=True)).sum() == 0
    assert rule_eligible(x, Design(0)).sum() == 0


def test_quote_arithmetic_with_known_model():
    eng = Engine(_FlatModel(), holdout=0.10)
    q = eng.quote(_x(1000), Design(60), aov=400, baskets=np.full(50, 400.0))
    # 1,000 visits, 900 shown: 0.05 x 900 = 45 extra orders; redemptions 0.15 x 900 = 135
    assert q["extra_orders"] == pytest.approx(45, abs=0.1)
    assert q["redemptions"] == pytest.approx(135, abs=0.1)
    gain = 900 * (0.15 * order_money(400, 60).restaurant_profit - 0.10 * order_money(400).restaurant_profit)
    assert q["profit_change"] == pytest.approx(gain, abs=1)
    assert q["anyway_share"] == pytest.approx(1 - 45 / 135, abs=1e-3)


def test_no_offer_quote_has_zero_range():
    """TL-030: "No offer" is exactly ₹0, not ₹0 with a ±₹3 range."""
    q = Engine(_FlatModel()).quote(_x(100), Design(0.0), aov=400, baskets=np.full(50, 400.0))
    assert q["profit_change"] == q["profit_low"] == q["profit_high"] == 0


def test_measure_recovers_a_known_effect():
    rng = np.random.default_rng(0)
    n = 40000
    hold = rng.random(n) < 0.10
    chosen = rng.random(n) < np.where(hold, 0.10, 0.15)
    rows = pd.DataFrame({"shown": ~hold, "holdout": hold, "chosen": chosen, "takes": ~hold,
                         "profit": np.where(hold, 134.0, 91.7), "basket": 400.0, "discount": np.where(hold, 0, 60.0)})
    eng = Engine(_FlatModel(), sigma_rel=1.0, sigma_orders=1.0)  # weak prior: data dominates
    m = eng.measure(rows, 400, prior_profit=0.0, prior_orders=0.0)
    true_per_visit = 0.15 * 91.7 - 0.10 * 134
    assert m["profit"]["low"] <= true_per_visit * (~hold).sum() <= m["profit"]["high"]
    assert m["orders"]["per_visit"] == pytest.approx(0.05, abs=0.01)
    assert m["report_today"]["orders_with_offer"] == int((chosen & ~hold).sum())


def test_measure_handles_tiny_groups():
    rows = pd.DataFrame({"shown": [True], "holdout": [False], "chosen": [True], "takes": [True],
                         "profit": [90.0], "basket": [400.0], "discount": [60.0]})
    m = Engine(_FlatModel(), sigma_rel=0.01).measure(rows, 400, prior_profit=2.0, prior_orders=0.01)
    assert m["profit"]["weight_on_own_data"] == 0.0  # too little data: the prior alone
    assert m["profit"]["per_visit"] == pytest.approx(2.0)


def test_auto_pause_fires_on_a_clearly_losing_offer():
    """TL-009's missing test: a large, clearly negative effect gives the pause verdict."""
    rng = np.random.default_rng(1)
    n = 20000
    hold = rng.random(n) < 0.10
    chosen = rng.random(n) < 0.10  # the offer adds no orders...
    rows = pd.DataFrame({"shown": ~hold, "holdout": hold, "chosen": chosen, "takes": ~hold & chosen,
                         "profit": np.where(hold, 134.0, 40.0),  # ...and gives away margin on every one
                         "basket": 400.0, "discount": np.where(hold, 0, 150.0)})
    m = Engine(_FlatModel(), sigma_rel=1.0, sigma_orders=1.0).measure(rows, 400, -5.0, 0.0)
    assert m["verdict_code"] == "pause"
    assert m["profit"]["high"] < 0


def test_calibrate_floors_negative_variance():
    offers = pd.DataFrame({"own_profit": [1.0, 1.0], "prior_profit": [1.0, 1.0], "se_profit": [5.0, 5.0],
                           "own_orders": [0.0, 0.0], "prior_orders": [0.0, 0.0], "se_orders": [1.0, 1.0],
                           "aov": [400.0, 400.0]})
    eng = Engine(_FlatModel())
    rel, orders = eng.calibrate(offers)
    assert rel == pytest.approx(0.002) and orders == pytest.approx(0.0005)


def test_offer_mix_edges():
    b = np.array([200.0, 300.0, 400.0])
    assert offer_mix(b, 0, 0, 300, 0.5) == (0.0, 300.0, 300.0, 300.0)
    use, take, skip, usual = offer_mix(b, 60, 0, 300, 0.5)  # no minimum: everyone uses it
    assert use == 1.0 and take == pytest.approx(300.0)
    use, take, skip, usual = offer_mix(b, 60, 10_000, 300, 0.5)  # unreachable minimum: nobody does
    assert use == 0.0
    assert offer_mix(np.array([]), 60, 0, 350, 0.5)[3] == 350  # no history: the average order


def test_design_options_are_the_grid_the_engine_compares():
    for aov in (150, 180, 420, 450, 660, 700, 1000):
        o = design_options(aov)
        assert o["default_depth"] in o["depths"]
        grid = Engine(_FlatModel()).design_grid(aov, Design(o["default_depth"]))
        assert {d.min_order for d in grid[3:]} == {0.0, float(o["min_order"])}
        assert {d.reward for d in grid[3:]} == {0.0, float(o["reward"])}
        assert len(grid) == 35  # owner, no offer, Brand Pack only, 32 versions


def test_prediction_cache_rejects_misuse():
    cache: dict = {}
    _cached(cache, ("p0", 0.0), lambda: np.zeros(5), 5)
    with pytest.raises(RuntimeError, match="cache misuse"):
        _cached(cache, ("p0", 0.0), lambda: np.zeros(3), 3)


def _table_x(n_cust=6):
    c = np.tile(np.arange(n_cust), 3)
    df = _x(len(c))
    df["slot"] = np.repeat(np.arange(3), n_cust)
    df.insert(0, "cust", c)
    return df


def test_decision_table_matches_per_visit_decisions():
    eng = Engine(_FlatModel())
    x = _table_x()
    d = Design(60, audience="new_to_restaurant", offpeak_only=True)
    t = eng.decision_table(x, d, 400, np.full(10, 400.0), offer_id=7)
    expected = rule_eligible(x.drop(columns=["cust"]), d)
    got = np.array([t.lookup(c, s)[0] for c, s in zip(x["cust"], x["slot"], strict=True)])
    assert np.array_equal(got, expected)
    assert t.lookup(999, 1)[4].startswith("new visitor")


def test_serve_from_table_applies_the_shared_holdout():
    from truelift.assignment import in_control_group
    eng = Engine(_FlatModel(), holdout=0.5)
    x = _table_x(40)
    t = eng.decision_table(x, Design(60), 400, np.full(10, 400.0), offer_id=3)
    for c in range(40):
        out = eng.serve(t, c, 2, regular=False)
        assert out["control_group"] == bool(in_control_group(c, 3, 0.5)[0])
        assert out["show_offer"] == (not out["control_group"])


def test_decision_table_falls_back_to_the_owners_rule_and_says_so():
    eng = Engine(_BrokenModel())
    x = _table_x()
    t = eng.decision_table(x, Design(60, audience="targeted"), 400, np.full(10, 400.0), offer_id=1)
    assert t.degraded and eng.fallbacks == 1
    assert eng.serve(t, 0, 2, False)["degraded"] is True


def test_weekly_message_uses_one_money_format_and_says_what_to_do():
    m = {"orders": {"low": -2, "high": 30, "total": 12}, "profit": {"low": -1234, "high": 3500, "total": 900},
         "report_today": {"orders_with_offer": 40}, "verdict_code": "wait"}
    text = weekly_message("Burger King", 2, m, Design(60), holdout=0.10)
    assert "−₹1,234 to +₹3,500" in text and "₹-" not in text
    assert "1 in 10" in text and "Too early to say" in text
    assert "Reply 1" not in text  # replies that do nothing are gone (TL-032)
    paused = weekly_message("X", 2, {**m, "verdict_code": "pause"}, Design(60), holdout=0.20)
    assert "paused" in paused and "1 in 5" in paused
