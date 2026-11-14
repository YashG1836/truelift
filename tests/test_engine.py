"""The engine's decisions with a model whose answers are known in advance."""

from __future__ import annotations

import math

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
    return pd.DataFrame(
        {
            "slot": np.full(n, 2),
            "cr_orders_all": np.r_[np.zeros(n // 2), np.ones(n - n // 2)],
            "cr_weeks_since": np.full(n, 6.0),
            "cr_orders_4w": np.zeros(n),
            "c_no_order_8w": np.zeros(n),
            "c_new_account": np.zeros(n),
            "reward": np.zeros(n),
        }
    )


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
    rows = pd.DataFrame(
        {
            "shown": ~hold,
            "holdout": hold,
            "chosen": chosen,
            "takes": ~hold,
            "profit": np.where(hold, 134.0, 91.7),
            "basket": 400.0,
            "discount": np.where(hold, 0, 60.0),
        }
    )
    eng = Engine(_FlatModel(), sigma_rel=1.0, sigma_orders=1.0)  # weak prior: data dominates
    m = eng.measure(rows, 400, prior_profit=0.0, prior_orders=0.0)
    true_per_visit = 0.15 * 91.7 - 0.10 * 134
    assert m["profit"]["low"] <= true_per_visit * (~hold).sum() <= m["profit"]["high"]
    assert m["orders"]["per_visit"] == pytest.approx(0.05, abs=0.01)
    assert m["report_today"]["orders_with_offer"] == int((chosen & ~hold).sum())


def test_measure_handles_tiny_groups():
    rows = pd.DataFrame(
        {
            "shown": [True],
            "holdout": [False],
            "chosen": [True],
            "takes": [True],
            "profit": [90.0],
            "basket": [400.0],
            "discount": [60.0],
        }
    )
    m = Engine(_FlatModel(), sigma_rel=0.01).measure(rows, 400, prior_profit=2.0, prior_orders=0.01)
    assert m["profit"]["weight_on_own_data"] == 0.0  # too little data: the prior alone
    assert m["profit"]["per_visit"] == pytest.approx(2.0)


def test_auto_pause_fires_on_a_clearly_losing_offer():
    """TL-009's missing test: a large, clearly negative effect gives the pause verdict."""
    rng = np.random.default_rng(1)
    n = 20000
    hold = rng.random(n) < 0.10
    chosen = rng.random(n) < 0.10  # the offer adds no orders...
    rows = pd.DataFrame(
        {
            "shown": ~hold,
            "holdout": hold,
            "chosen": chosen,
            "takes": ~hold & chosen,
            "profit": np.where(hold, 134.0, 40.0),  # ...and gives away margin on every one
            "basket": 400.0,
            "discount": np.where(hold, 0, 150.0),
        }
    )
    m = Engine(_FlatModel(), sigma_rel=1.0, sigma_orders=1.0).measure(rows, 400, -5.0, 0.0)
    assert m["verdict_code"] == "pause"
    assert m["profit"]["high"] < 0


def test_calibrate_floors_negative_variance():
    offers = pd.DataFrame(
        {
            "own_profit": [1.0, 1.0],
            "prior_profit": [1.0, 1.0],
            "se_profit": [5.0, 5.0],
            "own_orders": [0.0, 0.0],
            "prior_orders": [0.0, 0.0],
            "se_orders": [1.0, 1.0],
            "aov": [400.0, 400.0],
        }
    )
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
    m = {
        "orders": {"low": -2, "high": 30, "total": 12},
        "profit": {"low": -1234, "high": 3500, "total": 900},
        "report_today": {"orders_with_offer": 40},
        "verdict_code": "wait",
    }
    text = weekly_message("Burger King", 2, m, Design(60), holdout=0.10)
    assert "−₹1,234 to +₹3,500" in text and "₹-" not in text
    assert "1 in 10" in text and "Too early to say" in text
    assert "Reply 1" not in text  # replies that do nothing are gone (TL-032)
    paused = weekly_message("X", 2, {**m, "verdict_code": "pause"}, Design(60), holdout=0.20)
    assert "paused" in paused and "1 in 5" in paused


class _NewCustomerModel(_FlatModel):
    """Offer works only on customers who never ordered from the restaurant (uplift known)."""

    def p1(self, x, discount, min_order):
        return np.where(x["cr_orders_all"].to_numpy() == 0, 0.30, 0.10)


class _ExplodingModel(_FlatModel):
    def p0(self, x):
        raise AssertionError("serve must not call the model")

    def p1(self, x, discount, min_order):
        raise AssertionError("serve must not call the model")


def test_targeted_table_matches_the_models_decisions():
    """WP-40: the table built at approval says exactly what the model says for every row."""
    eng = Engine(_NewCustomerModel())
    x = _table_x(20)
    d = Design(60, audience="targeted")
    t = eng.decision_table(x, d, 400, np.full(10, 400.0), offer_id=5)
    want = eng.design_values(x.drop(columns=["cust"]), d, 400, np.full(10, 400.0))["eligible"]
    got = np.array([t.lookup(c, s)[0] for c, s in zip(x["cust"], x["slot"], strict=True)])
    assert np.array_equal(got, want)
    assert got.any() and not got.all()  # the model separates the two groups


def test_serve_never_calls_the_model():
    """TL-001 / TL-005: serving is a table lookup plus the holdout hash, never a prediction."""
    eng = Engine(_FlatModel())
    t = eng.decision_table(_table_x(), Design(60, audience="targeted"), 400, np.full(10, 400.0), offer_id=9)
    eng.model = _ExplodingModel()
    for c in range(6):
        out = eng.serve(t, c, 2, regular=False)
        assert out["degraded"] is False
    eng.serve(t, 999, 2, regular=False)  # unseen customer: the table's default, still no model call


def test_empty_visit_tables_are_handled():
    """A narrow design can have no eligible visit in a week: no crash, zeros (found by CI)."""
    from truelift.model import UpliftModel

    assert len(UpliftModel(None, None).p0(pd.DataFrame())) == 0  # type: ignore[arg-type]
    eng = Engine(_FlatModel())
    q = eng.quote(_x(0), Design(60, audience="targeted"), aov=400, baskets=np.full(5, 400.0))
    assert q["extra_orders"] == 0 and q["profit_change"] == 0
    m = eng.measure(
        pd.DataFrame(columns=["shown", "holdout", "chosen", "takes", "profit", "basket", "discount"]).astype(
            {"shown": bool, "holdout": bool, "chosen": bool, "takes": bool}
        ),
        400,
        0.0,
        0.0,
    )
    assert m["verdict_code"] == "wait" and m["profit"]["total"] == 0


def test_topup_fit_recovers_a_known_value_from_visit_counts():
    """TL-020: with skip-orders generated from a known top-up value, the visit-level fit finds it."""
    from truelift.engine import fit_topup_value

    rng = np.random.default_rng(3)
    baskets = [rng.lognormal(np.log(400), 0.3, 300) for _ in range(30)]
    rows = []
    for r in range(30):
        mov, disc = 449.0, 60.0
        use = offer_mix(baskets[r], disc, mov, 0.0, 0.3)[0]
        expected = 40.0
        rows.append(
            {
                "rest": r,
                "discount": disc,
                "min_order": mov,
                "skip_orders": (1 - use) * expected,
                "expected_orders": expected,
            }
        )
    value, (lo, hi) = fit_topup_value(pd.DataFrame(rows), baskets)
    assert value == pytest.approx(0.3, abs=0.03)
    assert lo <= value <= hi


def test_bigger_discount_never_lowers_the_predicted_chance(small_trained):
    """WP-24: with monotone constraints, more rupees off never predicts fewer orders."""
    x = small_trained.train.sample(300, random_state=0).reset_index(drop=True)
    model = small_trained.model
    preds = np.column_stack([model.p1(x, np.full(len(x), d), np.zeros(len(x))) for d in (20, 40, 60, 90, 150)])
    assert (np.diff(preds, axis=1) >= -1e-12).all()
    rewards = np.column_stack([model.p0(x.assign(reward=r)) for r in (0, 10, 30)])
    assert (np.diff(rewards, axis=1) >= -1e-12).all()


class _LosingModel(_FlatModel):
    """Every offer adds almost nothing: each version loses money on discounts given away."""

    def p1(self, x, discount, min_order):
        return np.full(len(x), 0.101)


def test_no_offer_is_chosen_when_every_version_loses():
    """TL-018: when no version is likely to make money, TrueLift recommends no offer."""
    eng = Engine(_LosingModel())
    owner_q, best = eng.best_design(_x(400), Design(60), 400, np.full(50, 400.0))
    assert best["design"]["discount"] == 0 and best["design"]["reward"] == 0
    assert owner_q["profit_change"] < 0 and best["profit_change"] == 0


def test_chance_of_making_money_matches_the_range():
    q = {"profit_change": 0, "profit_low": -100, "profit_high": 100}
    assert Engine.prob_profit_positive(q) == pytest.approx(0.5)
    q = {"profit_change": 100, "profit_low": 0, "profit_high": 200}  # low end = 0 -> 90% chance
    assert Engine.prob_profit_positive(q) == pytest.approx(0.9, abs=1e-3)
    assert Engine.prob_profit_positive({"profit_change": 0, "profit_low": 0, "profit_high": 0}) == 0.0


def test_gain_calibration_scales_each_side_and_keeps_signs():
    from truelift.training import gain_calibration

    rows = []
    for _ in range(30):
        rows.append({"subset": "targeted", "visits": 100, "own_profit": 1.8, "prior_profit": 2.0})
        rows.append({"subset": "excluded", "visits": 100, "own_profit": -0.5, "prior_profit": -1.0})
    pos, neg = gain_calibration(pd.DataFrame(rows))
    assert pos == pytest.approx(0.9) and neg == pytest.approx(0.5)
    eng = Engine(_FlatModel())
    eng.gain_scale = (pos, neg)
    v = eng.row_values(_x(4), 60.0, 0.0, 0.0, 0.0, (1.0, 400.0, 400.0, 400.0))
    raw = Engine(_FlatModel()).row_values(_x(4), 60.0, 0.0, 0.0, 0.0, (1.0, 400.0, 400.0, 400.0))
    assert np.array_equal(np.sign(v["gain"]), np.sign(raw["gain"]))


def _rows(n, rng, effect=0.0, share=0.10, customers=None):
    cust = rng.integers(0, customers or n, n)
    from truelift.assignment import stable_uniform

    hold = stable_uniform(cust, np.full(n, 7), 2) < share
    p = np.where(hold, 0.10, 0.10 + effect)
    chosen = rng.random(n) < p
    return pd.DataFrame(
        {
            "cust": cust,
            "shown": ~hold,
            "holdout": hold,
            "chosen": chosen,
            "takes": ~hold & chosen,
            "profit": np.full(n, 100.0),
            "basket": 400.0,
            "discount": np.where(hold, 0.0, 40.0),
        }
    )


def test_zero_order_control_group_does_not_look_certain():
    """A/A finding: a control group with no orders must not make a noisy difference look certain."""
    from truelift.engine import effect_and_se

    y = np.r_[np.full(50, 0.0), np.where(np.arange(450) % 10 == 0, 100.0, 0.0)]
    held = np.r_[np.ones(50, bool), np.zeros(450, bool)]
    cust = np.arange(500)
    noise = np.full(500, 0.1 * 0.9 * 100.0**2)
    _, se_sample = effect_and_se(y, ~held, held, cust, min_events=0)
    _, se_model = effect_and_se(y, ~held, held, cust, noise=noise, noise_scale=1.0)
    assert se_model > 2 * se_sample  # the sample variance of a group with no orders is zero
    assert effect_and_se(y, ~held, held, cust)[1] == float("inf")  # without the model: too few orders


def test_confidence_sequence_is_wider_than_a_fixed_interval_and_never_shrinks_below_it():
    from truelift.engine import cs_halfwidth, cs_rho

    rho = cs_rho(1.0, 1000)
    for n in (10, 100, 1000, 10000):
        se = 30.0 / math.sqrt(n)
        assert cs_halfwidth(se, n, rho) > 1.96 * se  # wider than a one-look 95% bound, at every n
    assert cs_halfwidth(float("inf"), 100, rho) == float("inf")


def test_sample_ratio_check_flags_a_broken_split():
    from truelift.engine import sample_ratio

    rng = np.random.default_rng(1)
    good = _rows(20000, rng)
    assert sample_ratio(good, 0.10)["ok"]
    broken = good.copy()
    broken.loc[broken.index[:4000], "holdout"] = True  # a logging fault adds controls
    broken["shown"] = ~broken["holdout"]
    assert not sample_ratio(broken, 0.10)["ok"]


def test_stratified_effect_compares_within_each_holdout_period():
    """Periods with different holdout shares are compared separately, then combined."""
    from truelift.engine import stratified_effect

    rng = np.random.default_rng(2)
    a = _rows(30000, rng, effect=0.05, share=0.30)
    b = _rows(30000, rng, effect=0.05, share=0.10)
    rows = pd.concat([a.assign(share=0.3, profit=200.0), b.assign(share=0.1)], ignore_index=True)
    y = rows["chosen"].to_numpy() * 1.0
    est, se = stratified_effect(
        y,
        rows["shown"].to_numpy(),
        rows["holdout"].to_numpy(),
        rows["cust"].to_numpy(),
        None,
        rows["share"].to_numpy(),
        adjust="fixed",
    )
    assert est == pytest.approx(0.05, abs=3 * se)


def test_pause_needs_its_own_evidence_and_a_real_control_group():
    """TL-017: a strongly losing offer is paused; a tiny control group never pauses anything."""
    rng = np.random.default_rng(3)
    eng = Engine(_FlatModel(), sigma_rel=1.0, sigma_orders=1.0)
    big = _rows(40000, rng, effect=-0.05, customers=20000)
    big["profit"] = np.where(big["holdout"], 134.0, 40.0)
    m = eng.measure(big, 400, -5.0, 0.0)
    assert m["verdict_code"] == "pause" and m["pause_check"]["control_customers"] >= 30
    small = big.iloc[:150]
    m2 = eng.measure(small, 400, -5.0, 0.0)
    assert m2["pause_check"]["control_customers"] < 30 and m2["verdict_code"] != "pause"


def test_probably_losing_warns_without_pausing():
    from truelift.engine import PROBABLY_LOSING

    eng = Engine(_FlatModel(), sigma_rel=0.01)
    rows = _rows(400, np.random.default_rng(4))
    m = eng.measure(rows, 400, prior_profit=-3.0, prior_orders=0.0)  # the model expects a loss
    assert 1 - m["profit"]["prob_positive"] > PROBABLY_LOSING
    assert m["verdict_code"] == "probably_losing"


def test_noise_scale_from_split_halves():
    from truelift.training import noise_scale

    rng = np.random.default_rng(5)
    rows = []
    for _ in range(200):  # true variance of a full estimate: 4.0; the model says 2.0
        rows.append(
            {
                "subset": "all",
                "half_diff_profit": rng.normal(0, 4.0),
                "expected_var_profit": 2.0,
                "half_diff_orders": rng.normal(0, 2.0),
                "expected_var_orders": 1.0,
            }
        )
    p, o = noise_scale(pd.DataFrame(rows))
    assert p == pytest.approx(2.0, rel=0.25) and o == pytest.approx(1.0, rel=0.25)


def test_quote_states_the_smallest_detectable_effect():
    eng = Engine(_FlatModel())
    eng.visit_noise_rel = 0.08
    q = eng.quote(_x(1000), Design(60), aov=400, baskets=np.full(50, 400.0))
    assert q["detectable_effect_4w"] is not None and q["detectable_effect_4w"] > 0
    assert Engine(_FlatModel()).quote(_x(1000), Design(60), 400, np.full(50, 400.0))["detectable_effect_4w"] is None


def test_brand_pack_line_recovers_a_known_effect():
    """TL-016: regulars who get the reward against regulars held out of it, per visit and in total."""
    from truelift.engine import measure_reward

    rng = np.random.default_rng(12)
    n = 60000
    cust = rng.integers(0, 20000, n)
    from truelift.assignment import stable_uniform

    held = stable_uniform(cust, np.full(n, 3), 3) < 0.10
    chosen = rng.random(n) < np.where(held, 0.30, 0.36)
    rows = pd.DataFrame(
        {"cust": cust, "reward_holdout": held, "chosen": chosen, "profit": np.where(held, 120.0, 100.0)}
    )
    bp = measure_reward(rows)
    o = bp["orders"]
    assert o["low"] <= 0.06 * (~held).sum() <= o["high"]
    assert bp["control_visits"] == int(held.sum()) and bp["verdict_code"] in {"pays", "costs", "unclear"}
    assert measure_reward(rows.iloc[:30])["verdict_code"] == "too_early"
    assert measure_reward(rows.iloc[:0]) is None
