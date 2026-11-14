"""The money of one order: hand-checked examples and laws that hold for every order."""
from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from truelift.economics import Terms, fmt_inr, order_money, split, weekly_example


# ---------- hand calculations ----------
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


def test_order_money_rejects_impossible_orders():
    with pytest.raises(ValueError):
        order_money(100, 150)
    with pytest.raises(ValueError):
        order_money(400, 60, zomato_share=1.5)


@pytest.mark.parametrize("x, sign, expected", [
    (0, False, "₹0"), (1234, False, "₹1,234"), (123456, False, "₹1,23,456"), (12345678, False, "₹1,23,45,678"),
    (-1234, False, "−₹1,234"), (2101, True, "+₹2,101"), (-210, True, "−₹210"), (999.6, False, "₹1,000"),
])
def test_money_format_matches_the_page(x, sign, expected):
    assert fmt_inr(x, sign) == expected


# ---------- laws for every order (property-based) ----------
baskets = st.floats(min_value=100, max_value=3000, allow_nan=False)
shares = st.floats(min_value=0, max_value=1, allow_nan=False)
bases = st.sampled_from(["post_discount", "pre_discount"])


@settings(max_examples=200, derandomize=True)
@given(basket=baskets, frac=shares, zshare=shares, base=bases)
def test_money_is_conserved(basket, frac, zshare, base):
    t = Terms(commission_on=base)
    discount = basket * frac
    m = split(basket, discount, zshare, t)
    assert m["customer_pays"] + m["discount"] == pytest.approx(basket)
    parts = m["restaurant_profit"] + m["commission"] + m["gst_on_commission"] + m["food_cost"] + m["restaurant_funded"]
    assert parts == pytest.approx(basket)
    assert m["zomato_gross"] == pytest.approx(m["commission"] - m["zomato_funded"])
    assert m["restaurant_funded"] + m["zomato_funded"] == pytest.approx(discount)


@settings(max_examples=200, derandomize=True)
@given(basket=baskets, a=shares, b=shares, base=bases)
def test_profit_never_rises_with_a_bigger_restaurant_funded_discount(basket, a, b, base):
    t = Terms(commission_on=base)
    lo, hi = sorted((a * basket * 0.6, b * basket * 0.6))
    assert split(basket, hi, 0.0, t)["restaurant_profit"] <= split(basket, lo, 0.0, t)["restaurant_profit"] + 1e-9


@settings(max_examples=200, derandomize=True)
@given(basket=baskets, frac=st.floats(min_value=0.01, max_value=0.4), base=bases)
def test_break_even_share_formula(basket, frac, base):
    """At the break-even share f of extra orders, the week's change is exactly zero:
    f x profit_discounted = (1 - f) x (profit_full - profit_discounted)."""
    t = Terms(commission_on=base)
    full = split(basket, 0.0, 0.0, t)["restaurant_profit"]
    disc = split(basket, basket * frac, 0.0, t)["restaurant_profit"]
    if disc <= 0:
        return  # an offer that loses money on every order never breaks even
    f = 1 - disc / full
    assert f * disc - (1 - f) * (full - disc) == pytest.approx(0.0, abs=1e-6)
