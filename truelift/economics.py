"""Money flows of one food-delivery order. Single source of truth for every rupee figure.

All amounts are rupees. "basket" is the menu value of the items before any discount.

Assumptions (each one is a parameter, see Terms):
- Commission 25% of the commission base, plus 18% GST on the commission. The restaurant pays both.
  (Restaurants on the 5% GST scheme cannot claim this GST back, so it is a real cost.)
- Commission base is the bill after the discount ("post_discount"). Third-party calculators
  disagree on this, so "pre_discount" is supported and should be confirmed with Eternal.
- Food and packaging cost 37% of the basket (₹148 on a ₹400 basket, as in the Round 1 example).
- Zomato's gain from an extra order is shown three ways, because its variable cost per order is
  not public: gross commission (upper bound), contribution at 8.5% of order value (last widely
  reported figure, FY25, unverified), and adjusted EBITDA at 5.5% of NOV (Q2 FY27, verified; a floor
  because it also covers fixed costs).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Terms:
    commission_rate: float = 0.25
    gst_on_commission: float = 0.18
    food_cost_share: float = 0.37
    commission_on: str = "post_discount"  # or "pre_discount"
    zomato_contribution_share: float = 0.085  # of customer bill; assumption
    zomato_ebitda_share: float = 0.055  # of customer bill; Eternal Q2 FY27 food delivery


@dataclass(frozen=True)
class OrderMoney:
    basket: float
    discount: float  # total discount on the order
    restaurant_funded: float  # part of the discount the restaurant pays
    zomato_funded: float  # part of the discount Zomato pays
    customer_pays: float  # food bill after discount (taxes and fees excluded)
    commission: float  # Zomato's gross commission
    gst_on_commission: float
    food_cost: float
    restaurant_profit: float  # basket - restaurant-funded discount - commission - GST - food cost
    zomato_gross: float  # commission - Zomato-funded discount
    zomato_contribution: float  # contribution share x bill - Zomato-funded discount
    zomato_ebitda: float  # EBITDA share x bill - Zomato-funded discount

    def as_dict(self) -> dict:
        return {k: round(v, 2) for k, v in asdict(self).items()}


def split(basket, discount, zomato_share, terms: Terms = Terms()) -> dict:
    """Vectorised money split; works on floats or numpy arrays of equal shape."""
    z_funded = discount * zomato_share
    r_funded = discount - z_funded
    bill = basket - discount
    base = bill if terms.commission_on == "post_discount" else basket
    commission = terms.commission_rate * base
    gst = terms.gst_on_commission * commission
    food = terms.food_cost_share * basket
    return {
        "basket": basket, "discount": discount, "restaurant_funded": r_funded,
        "zomato_funded": z_funded, "customer_pays": bill, "commission": commission,
        "gst_on_commission": gst, "food_cost": food,
        "restaurant_profit": basket - r_funded - commission - gst - food,
        "zomato_gross": commission - z_funded,
        "zomato_contribution": terms.zomato_contribution_share * bill - z_funded,
        "zomato_ebitda": terms.zomato_ebitda_share * bill - z_funded,
    }


def order_money(basket: float, discount: float = 0.0, zomato_share: float = 0.0,
                terms: Terms = Terms()) -> OrderMoney:
    """Split one order's money between customer, restaurant and Zomato.

    zomato_share is the fraction of the discount Zomato funds (0 for a restaurant-funded offer).
    """
    if discount < 0 or discount > basket:
        raise ValueError("discount must be between 0 and the basket value")
    if not 0.0 <= zomato_share <= 1.0:
        raise ValueError("zomato_share must be between 0 and 1")
    return OrderMoney(**{k: float(v) for k, v in split(basket, discount, zomato_share, terms).items()})


def weekly_example(terms: Terms = Terms(), basket: float = 400.0, discount: float = 60.0,
                   regulars: int = 70, new_orders: int = 30, rewards: float = 650.0) -> dict:
    """The Round 1 example, recomputed exactly with the given terms.

    One restaurant, one week: `regulars` orders arrive with or without an offer; a blanket offer
    adds `new_orders` new customers. TrueLift gives the discount only to the new customers and
    spends `rewards` on loyalty rewards for regulars (rewards don't reduce the bill).
    """
    full = order_money(basket, 0.0, terms=terms)
    disc = order_money(basket, discount, terms=terms)
    base_r = regulars * full.restaurant_profit
    base_z = regulars * full.commission
    blanket_r = (regulars + new_orders) * disc.restaurant_profit
    blanket_z = (regulars + new_orders) * disc.commission
    tl_r = regulars * full.restaurant_profit + new_orders * disc.restaurant_profit - rewards
    tl_z = regulars * full.commission + new_orders * disc.commission
    return {
        "per_order_full": full.as_dict(),
        "per_order_discounted": disc.as_dict(),
        "no_offer": {"restaurant_profit": base_r, "zomato_commission": base_z},
        "blanket": {
            "discount_spend": (regulars + new_orders) * discount,
            "discount_on_regulars": regulars * discount,
            "restaurant_profit": blanket_r, "restaurant_change": blanket_r - base_r,
            "zomato_commission": blanket_z, "zomato_change": blanket_z - base_z,
            "discount_per_extra_order": (regulars + new_orders) * discount / new_orders,
        },
        "truelift": {
            "discount_spend": new_orders * discount + rewards,
            "restaurant_profit": tl_r, "restaurant_change": tl_r - base_r,
            "zomato_commission": tl_z, "zomato_change": tl_z - base_z,
            "discount_per_extra_order": (new_orders * discount + rewards) / new_orders,
        },
    }
