"""Checks for the money maths, the simulator's truth, the measurement and the API flow.

Run: .venv/bin/python -m pytest -q
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from truelift.economics import Terms, order_money, weekly_example  # noqa: E402
from truelift.engine import Design, Engine, rule_eligible  # noqa: E402
from truelift.sim import Config, Market, Policy, stable_uniform  # noqa: E402


# ---------- money ----------
def test_order_money_matches_hand_calculation():
    full = order_money(400)
    assert full.commission == pytest.approx(100.0)
    assert full.gst_on_commission == pytest.approx(18.0)
    assert full.restaurant_profit == pytest.approx(400 - 100 - 18 - 148)  # 134
    disc = order_money(400, 60)
    assert disc.commission == pytest.approx(85.0)  # 25% of ₹340
    assert disc.restaurant_profit == pytest.approx(400 - 60 - 85 - 15.3 - 148)  # 91.7


def test_round1_example_exact():
    e = weekly_example()
    assert e["blanket"]["restaurant_change"] == pytest.approx(100 * 91.7 - 70 * 134)  # −210
    assert e["blanket"]["zomato_change"] == pytest.approx(100 * 85 - 70 * 100)  # +1,500
    assert e["truelift"]["restaurant_change"] == pytest.approx(30 * 91.7 - 650)  # +2,101
    assert e["truelift"]["zomato_change"] == pytest.approx(30 * 85)  # +2,550
    assert e["blanket"]["discount_per_extra_order"] == pytest.approx(200)


def test_commission_on_pre_discount_value():
    m = order_money(400, 60, terms=Terms(commission_on="pre_discount"))
    assert m.commission == pytest.approx(100.0)


def test_zomato_funded_discount_is_not_paid_by_restaurant():
    m = order_money(400, 60, zomato_share=0.5)
    assert m.restaurant_funded == pytest.approx(30)
    assert m.zomato_gross == pytest.approx(85 - 30)


# ---------- simulator ----------
@pytest.fixture(scope="module")
def market():
    R = pd.read_csv(ROOT / "data/processed/restaurants.csv")
    return Market(R, Config(customers_per_locality=300))


def _week(market, policy):
    from truelift.sim import History
    occ = market.occasions(1)
    return market.run_week(occ, policy, market.flat_features(History(), occ), salt=5)


def test_no_offer_has_no_effect(market):
    res = _week(market, Policy.none(market.n_rest))
    assert np.allclose(res["p"], res["p_cf"])
    assert np.allclose(res["platform_lift"], 0)


def test_probabilities_are_valid(market):
    n = market.n_rest
    pol = Policy(np.full(n, 60.0), np.zeros(n), np.zeros(n, bool), np.zeros(n), np.zeros(n),
                 np.array(["all"] * n, dtype=object), 0.10)
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


# ---------- engine ----------
class _FlatModel:
    """Stand-in model: 10% order chance without an offer, 15% with one."""
    def p0(self, x):
        return np.full(len(x), 0.10)

    def p1(self, x, discount, min_order):
        return np.full(len(x), 0.15)


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


# ---------- API (needs data/processed/model.pkl from scripts/run_pipeline.py) ----------
@pytest.mark.skipif(not (ROOT / "data/processed/model.pkl").exists(), reason="run the pipeline first")
def test_api_end_to_end():
    from fastapi.testclient import TestClient
    from truelift.api import app
    c = TestClient(app)
    rid = c.get("/api/restaurants").json()["demo_restaurant"]
    design = {"discount": 60, "min_order": 0, "audience": "targeted", "offpeak_only": False, "reward": 0, "zomato_share": 0}
    q = c.post("/api/quote", json={"restaurant_id": rid, "design": design}).json()
    assert q["owner"]["profit_low"] <= q["owner"]["profit_change"] <= q["owner"]["profit_high"]
    off = c.post("/api/offers", json={"restaurant_id": rid, "design": design}).json()
    oid = off["offer_id"]
    assert c.post(f"/api/offers/{oid}/approve", json={"otp": "0000"}).status_code == 403
    ok = c.post(f"/api/offers/{oid}/approve", json={"otp": off["demo_otp"]}).json()
    assert ok["status"] == "active" and ok["consent"]["forecast_shown"]["label"]
    cust = c.post("/api/customers", json={"restaurant_id": rid, "design": design}).json()["customers"]
    s = c.get("/api/serve", params={"restaurant_id": rid, "customer_id": cust[0]["customer_id"]}).json()
    assert "show_offer" in s and s["latency_ms"] < 200
    wk = c.post(f"/api/offers/{oid}/run_week").json()["weeks"][-1]
    p = wk["payout"]
    assert p["net_payout"] == (p["gross_sales"] - p["discount_paid_by_you"] - p["brand_pack_rewards_paid_by_you"]
                               - p["commission_25pct"] - p["gst_on_commission_18pct"])
    assert "Reply 1 to keep" in wk["whatsapp"]
