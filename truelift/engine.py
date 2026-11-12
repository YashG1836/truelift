"""TrueLift's four decisions inside Zomato's existing offer flow.

1. quote()    Before approval (the OTP screen): forecast extra orders and profit for the owner's
              offer, and compare 34 versions of it (audience, minimum order, time, Brand Pack).
2. serve()    While it runs: show the offer to a visiting customer only if it is expected to create
              profit; a random 10% of eligible customers never see it (the control group).
3. Funding    The restaurant pays for its own offer. Optionally Zomato co-funds the discount for
              customers new to Zomato, because Zomato gains the customer.
4. measure()  Every week: compare shown vs held-out customers, combine with the model, give a range,
              recommend keep / change / stop, auto-pause offers that clearly lose money.

Why combine with the model: a restaurant with ~50 orders a week has only ~5 held-out customers
ordering per week, too few to measure alone (see the precision table in the Round 2 plan). The model
learned from all restaurants gives a prior; the restaurant's own control group corrects it over time.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .economics import Terms, split
from .model import UpliftModel

Z80 = 1.2816  # half-width of an 80% interval, in standard deviations


@dataclass(frozen=True)
class Design:
    discount: float = 0.0  # ₹ off; 0 = no discount
    min_order: float = 0.0  # ₹; 0 = none
    audience: str = "all"  # all | new_to_restaurant | lapsed | targeted
    offpeak_only: bool = False  # valid 3-6 pm only
    reward: float = 0.0  # Brand Pack ₹ per order for regulars (3+ orders in 4 weeks)
    zomato_share: float = 0.0  # share of the discount Zomato funds for customers new to Zomato

    def label(self) -> str:
        if not self.discount:
            return f"No discount; ₹{self.reward:.0f} Brand Pack reward for regulars" if self.reward else "No offer"
        aud = {"all": "for everyone", "new_to_restaurant": "for customers new to you",
               "lapsed": "for customers who stopped ordering (4+ weeks)",
               "targeted": "only for customers it brings in"}[self.audience]
        parts = [f"₹{self.discount:.0f} off"]
        if self.min_order:
            parts.append(f"above ₹{self.min_order:.0f}")
        parts.append(aud)
        if self.offpeak_only:
            parts.append("(3-6 pm)")
        if self.reward:
            parts.append(f"+ ₹{self.reward:.0f} Brand Pack reward for regulars")
        if self.zomato_share:
            parts.append(f"(Zomato pays {self.zomato_share:.0%} for customers new to Zomato)")
        return " ".join(parts)


def rule_eligible(x: pd.DataFrame, d: Design) -> np.ndarray:
    """Who can see the discount under the owner's audience rule (before TrueLift's targeting)."""
    if d.discount <= 0:
        return np.zeros(len(x), bool)
    ok = np.ones(len(x), bool)
    if d.offpeak_only:
        ok &= x["slot"].to_numpy() == 1
    if d.audience == "new_to_restaurant":
        ok &= x["cr_orders_all"].to_numpy() == 0
    elif d.audience == "lapsed":
        ok &= (x["cr_orders_all"].to_numpy() > 0) & (x["cr_weeks_since"].to_numpy() >= 4)
    return ok


def offer_mix(baskets: np.ndarray, discount: float, min_order: float, aov: float,
              topup_value: float) -> tuple[float, float, float, float]:
    """How orders split when an offer has a minimum order.

    A customer whose usual basket b is below the minimum uses the offer only if the discount is
    worth more than the part of the top-up they don't value: discount > (1 - topup_value) x (min - b).
    topup_value is learned from past minimum-order offers (`fit_topup_value`).
    Returns (share of orders using the offer, basket when used, basket when not used, usual basket).
    """
    b = baskets if len(baskets) else np.array([aov])
    b0 = float(b.mean())
    if discount <= 0:
        return 0.0, b0, b0, b0
    uses = discount - (1 - topup_value) * np.maximum(0.0, min_order - b) > 0
    if not uses.any():
        return 0.0, b0, b0, b0
    take = float(np.maximum(b[uses], min_order).mean())
    skip = float(b[~uses].mean()) if (~uses).any() else b0
    return float(uses.mean()), take, skip, b0


def fit_topup_value(offers: pd.DataFrame, baskets: list) -> float:
    """Learn topup_value from past minimum-order offers: the value that best reproduces the share
    of their orders that actually used the offer. offers: rest, discount, min_order, use_rate, orders."""
    grid = np.linspace(0.0, 1.0, 41)
    err = []
    for g in grid:
        pred = np.array([offer_mix(baskets[int(r)], d, m, 0.0, g)[0] if len(baskets[int(r)]) else np.nan
                         for r, d, m in offers[["rest", "discount", "min_order"]].to_numpy()])
        ok = ~np.isnan(pred)
        err.append(float(np.sum(offers["orders"].to_numpy()[ok] * (pred[ok] - offers["use_rate"].to_numpy()[ok]) ** 2)))
    return float(grid[int(np.argmin(err))])


class Engine:
    def __init__(self, model: UpliftModel, terms: Terms = Terms(), sigma_rel: float = 0.02,
                 sigma_orders: float = 0.005, holdout: float = 0.10, topup_value: float = 0.5):
        self.model, self.terms, self.holdout, self.topup_value = model, terms, holdout, topup_value
        # model error of a restaurant's average effect per eligible visit (set by `calibrate`):
        # profit as a share of its average order value; orders in absolute terms
        self.sigma_rel, self.sigma_orders = sigma_rel, sigma_orders
        self._cache = None  # model predictions reused while one restaurant's designs are compared

    def _cached(self, key, fn) -> np.ndarray:
        """Reuse a prediction when the same design is scored again for the same visits."""
        if self._cache is None or None in key:
            return fn()
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    # ---------------- per-visit expectations (vectorised: one design per row) ----------------
    def row_values(self, x: pd.DataFrame, discount, min_order, reward, zomato_share, mix) -> dict:
        """Expected outcomes per menu visit with and without the discount shown.

        Design arguments are arrays aligned with x (or scalars). mix = (use rate, basket when the
        offer is used, basket when not, usual basket) for that visit's restaurant (`offer_mix`).
        """
        n = len(x)
        a = lambda v: np.broadcast_to(np.asarray(v, float), (n,))  # noqa: E731
        discount, min_order, reward, zomato_share = map(a, (discount, min_order, reward, zomato_share))
        use, b_take, b_skip, b0 = map(a, mix)
        regular = x["cr_orders_4w"].to_numpy() >= 3
        rw = np.where(regular, reward, 0.0)
        xr = x.assign(reward=rw)
        one = lambda v: float(v[0]) if n and np.all(v == v[0]) else None  # noqa: E731
        p0 = self._cached(("p0", one(reward)), lambda: self.model.p0(xr))
        has = discount > 0
        p1 = p0.copy()
        if has.all():
            p1 = self._cached(("p1", one(discount), one(min_order), one(reward)),
                              lambda: self.model.p1(xr, discount, min_order))
        elif has.any():
            p1[has] = self.model.p1(xr[has], discount[has], min_order[has])
        new_z = x["c_new_to_zomato"].to_numpy() == 1
        tot = discount + rw
        zs = np.where(new_z & (tot > 0), zomato_share * discount / np.maximum(tot, 1e-9), 0.0)
        use = np.where(has, use, 0.0)
        m0 = split(b0, rw, np.zeros(n), self.terms)
        mt = split(b_take, np.where(has, tot, rw), zs, self.terms)  # order that uses the offer
        ms = split(b_skip, rw, np.zeros(n), self.terms)  # shown, but basket too small to use it
        mix1 = lambda k: use * mt[k] + (1 - use) * ms[k]  # noqa: E731
        profit1 = np.where(has, mix1("restaurant_profit"), m0["restaurant_profit"])
        comm1 = np.where(has, mix1("commission"), m0["commission"])
        gain = p1 * profit1 - p0 * m0["restaurant_profit"]
        return {"p0": p0, "p1": p1, "gain": gain, "regular": regular, "reward": rw, "use": use,
                "profit0": m0["restaurant_profit"], "profit1": profit1, "comm0": m0["commission"],
                "comm1": comm1, "zfund1": use * mt["zomato_funded"],
                "basket1": np.where(has, use * b_take + (1 - use) * b_skip, b0)}

    def mix(self, baskets: np.ndarray, d: Design, aov: float) -> tuple:
        return offer_mix(baskets, d.discount, d.min_order, aov, self.topup_value)

    def design_values(self, x: pd.DataFrame, d: Design, aov: float, baskets: np.ndarray) -> dict:
        mx = self.mix(baskets, d, aov)
        v = self.row_values(x, d.discount, d.min_order, d.reward, d.zomato_share, mx)
        el = rule_eligible(x, d)
        if d.audience == "targeted":
            el &= v["gain"] > 0
        v.update(eligible=el, mix=mx)
        return v

    # ---------------- 1. quote ----------------
    def quote(self, x: pd.DataFrame, d: Design, aov: float, baskets: np.ndarray,
              weeks: float = 1.0) -> dict:
        """Forecast one week of an offer.

        x: the restaurant's recent menu visits with today's features, covering `weeks` weeks.
        """
        v = self.design_values(x, d, aov, baskets)
        el = v["eligible"]
        show = el * (1 - self.holdout)
        n_el = el.sum() / weeks
        redemptions = float((show * v["p1"] * v["use"]).sum() / weeks)
        extra_disc = float((show * (v["p1"] - v["p0"])).sum() / weeks)
        dprofit = float((show * v["gain"]).sum() / weeks)
        dcomm = float((show * (v["p1"] * v["comm1"] - v["p0"] * v["comm0"])).sum() / weeks)
        zfund = float((show * v["p1"] * v["zfund1"]).sum() / weeks)
        extra_rw = rw_cost = 0.0
        if d.reward > 0:  # Brand Pack effect on regulars who don't get the discount
            b0 = v["mix"][3]
            base = self.row_values(x, 0.0, 0.0, 0.0, 0.0, (0.0, b0, b0, b0))
            reg = v["regular"] & ~el
            dprofit += float(((v["p0"] * v["profit0"] - base["p0"] * base["profit0"]) * reg).sum() / weeks)
            extra_rw = float(((v["p0"] - base["p0"]) * reg).sum() / weeks)
            dcomm += float(((v["p0"] * v["comm0"] - base["p0"] * base["comm0"]) * reg).sum() / weeks)
            rw_cost = float((v["p0"] * v["reward"] * reg).sum() / weeks)
        spend = redemptions * d.discount
        extra = extra_disc + extra_rw
        shown_orders = float((show * v["p1"]).sum())
        order_value = float((show * v["p1"] * v["basket1"]).sum() / shown_orders) if shown_orders > 0 else v["mix"][3]
        sd = self.sigma_rel * aov * max(n_el * (1 - self.holdout), 1.0)
        return {
            "design": asdict(d), "label": d.label(),
            "menu_visits": round(len(x) / weeks), "eligible_visits": round(n_el),
            "redemptions": round(redemptions, 1), "extra_orders": round(extra, 1),
            "anyway_share": round(min(max(1 - extra_disc / redemptions, 0.0), 1.0), 3) if redemptions > 0 else None,
            "profit_change": round(dprofit), "profit_low": round(dprofit - Z80 * sd),
            "profit_high": round(dprofit + Z80 * sd),
            "discount_spend": round(spend), "reward_spend": round(rw_cost),
            "discount_per_extra_order": round((spend + rw_cost) / extra) if extra > 0.5 else None,
            "zomato_commission_change": round(dcomm), "zomato_funded": round(zfund),
            "offer_use_rate": round(float(v["mix"][0]), 3),
            "order_value_with_offer": round(order_value), "usual_order_value": round(v["mix"][3]),
        }

    def design_grid(self, aov: float, owner: Design) -> list[Design]:
        """The owner's design first, then 'no offer', 'Brand Pack only' and 32 versions at the owner's
        discount size: minimum order or not, 4 audiences, all day or 3-6 pm, Brand Pack or not.

        The discount size stays the owner's: past offers vary it only between restaurants, which is
        too little to learn how orders respond to ₹40 vs ₹60 vs ₹80 (in the simulator, letting the
        model pick the size lowered profit). A size change should come from a depth test that gives
        customers one size or the other at random.
        """
        mov = float(math.ceil(aov * 1.15 / 50) * 50 - 1)
        reward = float(max(5.0, round(aov * 0.05 / 5) * 5))
        grid = [owner, Design(0.0), Design(0.0, reward=reward)]
        if owner.discount <= 0:
            return grid
        for mo in (0.0, mov):
            for aud in ("all", "new_to_restaurant", "lapsed", "targeted"):
                for off in (False, True):
                    for rw in (0.0, reward):
                        grid.append(Design(owner.discount, mo, aud, off, rw, owner.zomato_share))
        return grid

    def best_design(self, x: pd.DataFrame, owner: Design, aov: float, baskets: np.ndarray,
                    weeks: float = 1.0) -> tuple[dict, dict]:
        """Quote for the owner's design and the best alternative (highest expected profit change).

        The owner still sees the range for both before approving.
        """
        self._cache = {}
        try:
            quotes = [self.quote(x, d, aov, baskets, weeks) for d in self.design_grid(aov, owner)]
        finally:
            self._cache = None
        best = max(quotes[1:], key=lambda q: (q["profit_change"], q["profit_low"]))
        best["designs_compared"] = len(quotes) - 1
        return quotes[0], best

    # ---------------- 2. serve ----------------
    def targeting_scorer(self, mixes: np.ndarray):
        """Scorer for the simulator: show a targeted offer only where expected profit gain > 0.

        mixes: array (restaurants, 4) of each restaurant's offer_mix for its current offer.
        """
        def score(feats: dict, policy, mask: np.ndarray) -> np.ndarray:
            x = pd.DataFrame({k: np.asarray(v)[mask] for k, v in feats.items()})
            rest = x.pop("rest").to_numpy().astype(int)
            mx = tuple(mixes[rest, i] for i in range(4))
            v = self.row_values(x, policy.discount[rest], policy.min_order[rest], policy.reward[rest],
                                policy.zomato_share[rest], mx)
            return v["gain"] > 0
        return score

    def serve(self, x_row: pd.DataFrame, d: Design, aov: float, baskets: np.ndarray,
              customer_id: int, offer_id: int) -> dict:
        """Decision for one customer opening the menu. Falls back to the owner's rule on any error."""
        from .sim import stable_uniform
        try:
            v = self.design_values(x_row, d, aov, baskets)
            el = bool(v["eligible"][0])
            if d.audience == "targeted":
                reason = "likely to order because of the offer" if el else "would order anyway or not at all"
            else:
                reason = "matches the owner's audience" if el else "outside the owner's audience"
            gain, p0, p1 = float(v["gain"][0]), float(v["p0"][0]), float(v["p1"][0])
        except Exception:  # fallback: behave like today's offer, which the owner consented to
            el, reason, gain, p0, p1 = bool(rule_eligible(x_row, d)[0]), "fallback: owner's rule", 0.0, 0.0, 0.0
        held = el and stable_uniform(np.array([customer_id]), np.array([offer_id]), 2)[0] < self.holdout
        regular = bool(x_row["cr_orders_4w"].iloc[0] >= 3)
        return {"show_offer": el and not held, "control_group": held, "reason": reason,
                "brand_pack_reward": d.reward if regular else 0.0,
                "p_order_without": round(p0, 4), "p_order_with": round(p1, 4),
                "expected_profit_gain": round(gain, 2)}

    # ---------------- 4. measure ----------------
    def measure(self, rows: pd.DataFrame, aov: float, prior_profit: float, prior_orders: float,
                base_profit=None, base_orders=None) -> dict:
        """Measured effect of an offer so far.

        rows: eligible visits, observed columns only: shown, holdout, chosen (ordered here), takes
        (used the offer), profit (restaurant profit of that order), basket, discount.
        prior_*: the model's average effect per eligible visit for the same visits.
        base_*: each visit's predicted outcome without the offer (from history only). Subtracting
        it before comparing shown and held-out visits keeps the comparison unbiased (assignment is
        random) and removes most of the noise from which customers happened to be held out
        (regression adjustment, as in CUPED).
        """
        t, c = rows["shown"].to_numpy(), rows["holdout"].to_numpy()
        n_t, n_c = int(t.sum()), int(c.sum())
        chosen = rows["chosen"].to_numpy()
        zero = np.zeros(len(rows))
        out = {"shown_visits": n_t, "control_visits": n_c}
        for key, y, prior, sig, base in (
            ("profit", chosen * rows["profit"].to_numpy(), prior_profit, self.sigma_rel * aov,
             zero if base_profit is None else np.asarray(base_profit)),
            ("orders", chosen.astype(float), prior_orders, self.sigma_orders,
             zero if base_orders is None else np.asarray(base_orders)),
        ):
            y = y - base
            if n_t >= 2 and n_c >= 2:
                own = float(y[t].mean() - y[c].mean())
                se = math.sqrt(y[t].var(ddof=1) / n_t + y[c].var(ddof=1) / n_c)
            else:
                own, se = 0.0, math.inf
            if math.isinf(se) or se == 0:
                post, psd, w = prior, sig, 0.0
            else:
                w = sig ** 2 / (sig ** 2 + se ** 2)
                post = w * own + (1 - w) * prior
                psd = math.sqrt(1 / (1 / sig ** 2 + 1 / se ** 2))
            out[key] = {"per_visit": post, "per_visit_sd": psd, "own_per_visit": own,
                        "own_se": None if math.isinf(se) else se, "model_per_visit": prior,
                        "weight_on_own_data": w, "total": post * n_t,
                        "low": (post - Z80 * psd) * n_t, "high": (post + Z80 * psd) * n_t}
        took = rows["takes"].to_numpy() & chosen
        out["report_today"] = {  # what a redemption report shows today
            "orders_with_offer": int(took.sum()),
            "sales_from_offer": float(rows["basket"].to_numpy()[took].sum()),
            "discount_given": float(rows["discount"].to_numpy()[took].sum()),
        }
        lo, hi = out["profit"]["low"], out["profit"]["high"]
        out["verdict"] = ("losing money: auto-pause" if hi < 0 else
                          "making money: keep" if lo > 0 else "too early to say: keep measuring")
        return out

    def calibrate(self, offers: pd.DataFrame) -> tuple[float, float]:
        """Set the model-error sizes from past offers that had a random holdout.

        offers: one row per offer with own_profit, se_profit, prior_profit, own_orders, se_orders,
        prior_orders (all per eligible visit) and aov. Priors must come from a model that did not
        see that restaurant (cross-fitting). Empirical Bayes: model error variance = spread of
        (own - prior) minus the sampling noise of the own estimates.
        """
        r = (offers["own_profit"] - offers["prior_profit"]) / offers["aov"]
        s = offers["se_profit"] / offers["aov"]
        self.sigma_rel = math.sqrt(max(float((r ** 2).mean() - (s ** 2).mean()), 0.002 ** 2))
        ro = offers["own_orders"] - offers["prior_orders"]
        so = offers["se_orders"]
        self.sigma_orders = math.sqrt(max(float((ro ** 2).mean() - (so ** 2).mean()), 0.0005 ** 2))
        return self.sigma_rel, self.sigma_orders


def weekly_message(name: str, week: int, m: dict, d: Design) -> str:
    """The WhatsApp summary to the owner, in plain words."""
    o, p, r = m["orders"], m["profit"], m["report_today"]
    return "\n".join([
        f"TrueLift weekly summary: {name}, week {week}",
        f"Offer: {d.label()}",
        f"Orders that used the offer: {r['orders_with_offer']}",
        f"Extra orders it created: {max(o['low'], 0):.0f} to {max(o['high'], 0):.0f} (best estimate {o['total']:.0f})",
        f"Extra profit for you: ₹{p['low']:,.0f} to ₹{p['high']:,.0f} (best estimate ₹{p['total']:,.0f})",
        "How we know: 1 in 10 eligible customers did not see the offer, and we compare the two groups.",
        f"Verdict: {m['verdict']}.",
        "Reply 1 to keep, 2 to change, 3 to stop.",
    ])
