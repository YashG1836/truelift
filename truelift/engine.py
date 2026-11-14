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

import logging
import math
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from .assignment import in_control_group
from .economics import Terms, fmt_inr, split
from .model import UpliftModel

Z80 = 1.2816  # half-width of an 80% interval, in standard deviations
log = logging.getLogger("truelift.engine")


def round_step(x: float, step: float) -> float:
    """Round to a multiple of `step`. The one rounding rule for every design option (audit TL-002):
    the page, the static export and the version grid all take their options from
    `design_options`, so they cannot disagree about which files exist."""
    return round(x / step) * step


def design_options(aov: float) -> dict:
    """The choices the create screen offers a restaurant with this average order value."""
    depths = sorted({max(20, int(round_step(aov * f, 10))) for f in (0.10, 0.15, 0.20, 0.25)})
    return {
        "depths": depths,
        "default_depth": max(20, int(round_step(aov * 0.15, 10))),
        "min_order": int(math.ceil(aov * 1.15 / 50) * 50 - 1),
        "reward": int(max(5, round_step(aov * 0.05, 5))),
    }


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
        aud = {
            "all": "for everyone",
            "new_to_restaurant": "for customers new to you",
            "lapsed": "for customers who stopped ordering (4+ weeks)",
            "targeted": "only for customers it brings in",
        }[self.audience]
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


def offer_mix(
    baskets: np.ndarray, discount: float, min_order: float, aov: float, topup_value: float
) -> tuple[float, float, float, float]:
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
        pred = np.array(
            [
                offer_mix(baskets[int(r)], d, m, 0.0, g)[0] if len(baskets[int(r)]) else np.nan
                for r, d, m in offers[["rest", "discount", "min_order"]].to_numpy()
            ]
        )
        ok = ~np.isnan(pred)
        err.append(float(np.sum(offers["orders"].to_numpy()[ok] * (pred[ok] - offers["use_rate"].to_numpy()[ok]) ** 2)))
    return float(grid[int(np.argmin(err))])


def _cached(cache: dict | None, key: tuple, fn: Callable[[], np.ndarray], n: int) -> np.ndarray:
    """Reuse a prediction when the same design is scored again for the same visits.

    The cache is a plain dictionary owned by one call of `best_design` (one restaurant, one set of
    visits) and passed down explicitly. Nothing is shared between requests, so concurrent quotes
    cannot read each other's predictions (audit TL-001). A hit is checked against the number of
    rows so a future misuse fails loudly instead of broadcasting.
    """
    if cache is None or None in key:
        return fn()
    if key not in cache:
        cache[key] = fn()
    value = cache[key]
    if len(value) != n:
        raise RuntimeError(f"prediction cache misuse: {len(value)} cached values for {n} visits")
    return value


@dataclass
class DecisionTable:
    """Who sees an approved offer, decided once at approval (and on each refresh), not per request.

    Keys are (customer, time slot) for every customer who can open this restaurant's menu. A menu
    request is then a dictionary lookup plus the holdout hash: no model on the request path, the
    decision is auditable afterwards, and a model failure cannot reach live traffic (audit A11 P2).
    """

    offer_id: int
    show: dict = field(default_factory=dict)  # (customer, slot) -> (eligible, p0, p1, gain, reason)
    default_eligible: bool = False  # for a customer the table has never seen
    degraded: bool = False  # the table was built with the owner's rule because scoring failed
    model_version: str = ""

    def lookup(self, customer_id: int, slot: int) -> tuple:
        hit = self.show.get((int(customer_id), int(slot)))
        if hit is None:
            return (self.default_eligible, 0.0, 0.0, 0.0, "new visitor: offer's default")
        return hit

    def eligible(self, customers: np.ndarray, slots: np.ndarray) -> np.ndarray:
        return np.array([self.lookup(c, s)[0] for c, s in zip(customers, slots, strict=True)], dtype=bool)


class Engine:
    def __init__(
        self,
        model: UpliftModel,
        terms: Terms = Terms(),
        sigma_rel: float = 0.02,
        sigma_orders: float = 0.005,
        holdout: float = 0.10,
        topup_value: float = 0.5,
    ):
        self.model, self.terms, self.holdout, self.topup_value = model, terms, holdout, topup_value
        # model error of a restaurant's average effect per eligible visit (set by `calibrate`):
        # profit as a share of its average order value; orders in absolute terms
        self.sigma_rel, self.sigma_orders = sigma_rel, sigma_orders
        self.model_version = ""
        self.fallbacks = 0  # serving decisions that fell back to the owner's rule (must stay 0)

    # ---------------- per-visit expectations (vectorised: one design per row) ----------------
    def row_values(
        self, x: pd.DataFrame, discount, min_order, reward, zomato_share, mix, cache: dict | None = None
    ) -> dict:
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
        p0 = _cached(cache, ("p0", one(reward)), lambda: self.model.p0(xr), n)
        has = discount > 0
        p1 = p0.copy()
        if has.all():
            p1 = _cached(
                cache,
                ("p1", one(discount), one(min_order), one(reward)),
                lambda: self.model.p1(xr, discount, min_order),
                n,
            )
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
        return {
            "p0": p0,
            "p1": p1,
            "gain": gain,
            "regular": regular,
            "reward": rw,
            "use": use,
            "profit0": m0["restaurant_profit"],
            "profit1": profit1,
            "comm0": m0["commission"],
            "comm1": comm1,
            "zfund1": use * mt["zomato_funded"],
            "basket1": np.where(has, use * b_take + (1 - use) * b_skip, b0),
        }

    def mix(self, baskets: np.ndarray, d: Design, aov: float) -> tuple:
        return offer_mix(baskets, d.discount, d.min_order, aov, self.topup_value)

    def design_values(
        self, x: pd.DataFrame, d: Design, aov: float, baskets: np.ndarray, cache: dict | None = None
    ) -> dict:
        """Per-visit expectations for one design, plus who is eligible: the owner's rule, and for a
        targeted design only the visits where the offer is expected to add profit."""
        mx = self.mix(baskets, d, aov)
        v = self.row_values(x, d.discount, d.min_order, d.reward, d.zomato_share, mx, cache=cache)
        el = rule_eligible(x, d)
        if d.audience == "targeted":
            el &= v["gain"] > 0
        v.update(eligible=el, mix=mx)
        return v

    # ---------------- 1. quote ----------------
    def quote(
        self, x: pd.DataFrame, d: Design, aov: float, baskets: np.ndarray, weeks: float = 1.0, cache: dict | None = None
    ) -> dict:
        """Forecast one week of an offer.

        x: the restaurant's recent menu visits with today's features, covering `weeks` weeks.
        """
        v = self.design_values(x, d, aov, baskets, cache=cache)
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
            base = self.row_values(x, 0.0, 0.0, 0.0, 0.0, (0.0, b0, b0, b0), cache=cache)
            reg = v["regular"] & ~el
            dprofit += float(((v["p0"] * v["profit0"] - base["p0"] * base["profit0"]) * reg).sum() / weeks)
            extra_rw = float(((v["p0"] - base["p0"]) * reg).sum() / weeks)
            dcomm += float(((v["p0"] * v["comm0"] - base["p0"] * base["comm0"]) * reg).sum() / weeks)
            rw_cost = float((v["p0"] * v["reward"] * reg).sum() / weeks)
        spend = redemptions * d.discount
        extra = extra_disc + extra_rw
        shown_orders = float((show * v["p1"]).sum())
        order_value = float((show * v["p1"] * v["basket1"]).sum() / shown_orders) if shown_orders > 0 else v["mix"][3]
        if d.discount <= 0 and d.reward <= 0:
            sd = 0.0  # "no offer" is exactly ₹0, with no range (audit TL-030)
        else:
            sd = self.sigma_rel * aov * max(n_el * (1 - self.holdout), 1.0)
        return {
            "design": asdict(d),
            "label": d.label(),
            "menu_visits": round(len(x) / weeks),
            "eligible_visits": round(n_el),
            "redemptions": round(redemptions, 1),
            "extra_orders": round(extra, 1),
            "anyway_share": round(min(max(1 - extra_disc / redemptions, 0.0), 1.0), 3) if redemptions > 0 else None,
            "profit_change": round(dprofit),
            "profit_low": round(dprofit - Z80 * sd),
            "profit_high": round(dprofit + Z80 * sd),
            "discount_spend": round(spend),
            "reward_spend": round(rw_cost),
            "discount_per_extra_order": round((spend + rw_cost) / extra) if extra > 0.5 else None,
            "zomato_commission_change": round(dcomm),
            "zomato_funded": round(zfund),
            "offer_use_rate": round(float(v["mix"][0]), 3),
            "order_value_with_offer": round(order_value),
            "usual_order_value": round(v["mix"][3]),
        }

    def design_grid(self, aov: float, owner: Design) -> list[Design]:
        """The owner's design first, then 'no offer', 'Brand Pack only' and 32 versions at the owner's
        discount size: minimum order or not, 4 audiences, all day or 3-6 pm, Brand Pack or not.

        The discount size stays the owner's: past offers vary it only between restaurants, which is
        too little to learn how orders respond to ₹40 vs ₹60 vs ₹80 (in the simulator, letting the
        model pick the size lowered profit). A size change should come from a depth test that gives
        customers one size or the other at random.
        """
        opts = design_options(aov)
        mov, reward = float(opts["min_order"]), float(opts["reward"])
        grid = [owner, Design(0.0), Design(0.0, reward=reward)]
        if owner.discount <= 0:
            return grid
        for mo in (0.0, mov):
            for aud in ("all", "new_to_restaurant", "lapsed", "targeted"):
                for off in (False, True):
                    for rw in (0.0, reward):
                        grid.append(Design(owner.discount, mo, aud, off, rw, owner.zomato_share))
        return grid

    def best_design(
        self, x: pd.DataFrame, owner: Design, aov: float, baskets: np.ndarray, weeks: float = 1.0
    ) -> tuple[dict, dict]:
        """Quote for the owner's design and the best alternative (highest expected profit change).

        The owner still sees the range for both before approving. Predictions are reused across the
        versions through a cache that lives only for this call.
        """
        cache: dict = {}
        quotes = [self.quote(x, d, aov, baskets, weeks, cache=cache) for d in self.design_grid(aov, owner)]
        best = max(quotes[1:], key=lambda q: (q["profit_change"], q["profit_low"]))
        best["designs_compared"] = len(quotes) - 1
        return quotes[0], best

    # ---------------- 2. serve ----------------
    def targeting_scorer(self, mixes: np.ndarray):
        """Scorer for the simulator: show a targeted offer only where expected profit gain > 0.

        mixes: array (restaurants, 4) of each restaurant's offer_mix for its current offer.
        """

        def score(feats: dict, policy, mask: np.ndarray) -> np.ndarray:
            x = pd.DataFrame({k: np.asarray(v)[mask] for k, v in feats.items() if k != "cust"})
            rest = x.pop("rest").to_numpy().astype(int)
            mx = tuple(mixes[rest, i] for i in range(4))
            v = self.row_values(
                x, policy.discount[rest], policy.min_order[rest], policy.reward[rest], policy.zomato_share[rest], mx
            )
            return v["gain"] > 0

        return score

    @staticmethod
    def _reasons(x: pd.DataFrame, d: Design, eligible: np.ndarray) -> list[str]:
        slot = x["slot"].to_numpy()
        out = []
        for i, el in enumerate(eligible):
            if d.discount <= 0:
                out.append("no discount in this offer")
            elif d.offpeak_only and slot[i] != 1:
                out.append("outside 3-6 pm, when the offer runs")
            elif d.audience == "targeted":
                out.append("likely to order because of the offer" if el else "would order anyway or not at all")
            else:
                out.append("matches the owner's audience" if el else "outside the owner's audience")
        return out

    def decision_table(
        self,
        x: pd.DataFrame,
        d: Design,
        aov: float,
        baskets: np.ndarray,
        offer_id: int,
        default_row: pd.DataFrame | None = None,
    ) -> DecisionTable:
        """Score every (customer, slot) that can open this restaurant's menu, once.

        x: one row per (customer, slot) with columns `cust`, `slot` and the features.
        default_row: the features of a customer with no history, which decide what a customer the
        table has never seen gets. If scoring fails the table falls back to the owner's own rule
        (what the owner consented to), is flagged as degraded, and the failure is logged and
        counted (audit TL-035).
        """
        table = DecisionTable(offer_id=int(offer_id), model_version=self.model_version)
        cust = x["cust"].to_numpy().astype(int)
        slot = x["slot"].to_numpy().astype(int)
        feats = x.drop(columns=["cust"])
        try:
            v = self.design_values(feats, d, aov, baskets)
            el, p0, p1, gain = v["eligible"], v["p0"], v["p1"], v["gain"]
            reasons = self._reasons(feats, d, el)
            if default_row is not None:
                table.default_eligible = bool(self.design_values(default_row, d, aov, baskets)["eligible"][0])
        except Exception:
            log.exception("decision table for offer %s fell back to the owner's rule", offer_id)
            self.fallbacks += 1
            table.degraded = True
            el = rule_eligible(feats, d)
            p0 = p1 = gain = np.zeros(len(feats))
            reasons = ["fallback: owner's rule"] * len(feats)
            table.default_eligible = d.audience in ("all", "new_to_restaurant") and d.discount > 0
        for i in range(len(cust)):
            table.show[(int(cust[i]), int(slot[i]))] = (
                bool(el[i]),
                float(p0[i]),
                float(p1[i]),
                float(gain[i]),
                reasons[i],
            )
        return table

    def serve(self, table: DecisionTable, customer_id: int, slot: int, regular: bool, reward: float = 0.0) -> dict:
        """Decision for one customer opening the menu: a table lookup and the shared holdout hash."""
        el, p0, p1, gain, reason = table.lookup(customer_id, slot)
        held = bool(el and in_control_group(customer_id, table.offer_id, self.holdout)[0])
        return {
            "show_offer": bool(el and not held),
            "control_group": held,
            "reason": reason,
            "brand_pack_reward": float(reward) if regular else 0.0,
            "p_order_without": round(p0, 4),
            "p_order_with": round(p1, 4),
            "expected_profit_gain": round(gain, 2),
            "degraded": table.degraded,
            "model_version": table.model_version,
        }

    # ---------------- 4. measure ----------------
    def measure(
        self,
        rows: pd.DataFrame,
        aov: float,
        prior_profit: float,
        prior_orders: float,
        base_profit=None,
        base_orders=None,
    ) -> dict:
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
            (
                "profit",
                chosen * rows["profit"].to_numpy(),
                prior_profit,
                self.sigma_rel * aov,
                zero if base_profit is None else np.asarray(base_profit),
            ),
            (
                "orders",
                chosen.astype(float),
                prior_orders,
                self.sigma_orders,
                zero if base_orders is None else np.asarray(base_orders),
            ),
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
                w = sig**2 / (sig**2 + se**2)
                post = w * own + (1 - w) * prior
                psd = math.sqrt(1 / (1 / sig**2 + 1 / se**2))
            out[key] = {
                "per_visit": post,
                "per_visit_sd": psd,
                "own_per_visit": own,
                "own_se": None if math.isinf(se) else se,
                "model_per_visit": prior,
                "weight_on_own_data": w,
                "total": post * n_t,
                "low": (post - Z80 * psd) * n_t,
                "high": (post + Z80 * psd) * n_t,
            }
        took = rows["takes"].to_numpy() & chosen
        out["report_today"] = {  # what a redemption report shows today
            "orders_with_offer": int(took.sum()),
            "sales_from_offer": float(rows["basket"].to_numpy()[took].sum()),
            "discount_given": float(rows["discount"].to_numpy()[took].sum()),
        }
        lo, hi = out["profit"]["low"], out["profit"]["high"]
        out["verdict_code"] = "pause" if hi < 0 else "keep" if lo > 0 else "wait"
        out["verdict"] = VERDICTS[out["verdict_code"]]
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
        self.sigma_rel = math.sqrt(max(float((r**2).mean() - (s**2).mean()), 0.002**2))
        ro = offers["own_orders"] - offers["prior_orders"]
        so = offers["se_orders"]
        self.sigma_orders = math.sqrt(max(float((ro**2).mean() - (so**2).mean()), 0.0005**2))
        return self.sigma_rel, self.sigma_orders


VERDICTS = {
    "keep": "making money: keep",
    "pause": "losing money: auto-pause",
    "wait": "too early to say: keep measuring",
}
VERDICT_SENTENCES = {
    "keep": "This offer is making you money. Keep it.",
    "pause": "This offer is losing money, so it has been paused.",
    "wait": "Too early to say. Keep it running; the range narrows every week.",
}


def weekly_message(name: str, week: int, m: dict, d: Design, holdout: float = 0.10) -> str:
    """The WhatsApp summary to the owner, in plain words, with the same money format as the page."""
    o, p, r = m["orders"], m["profit"], m["report_today"]
    one_in = max(int(round(1 / holdout)), 1) if holdout > 0 else 0
    return "\n".join(
        [
            f"TrueLift weekly summary: {name}, week {week}",
            f"Offer: {d.label()}",
            f"Orders that used the offer: {r['orders_with_offer']}",
            f"Extra orders it created: {max(o['low'], 0):.0f} to {max(o['high'], 0):.0f} "
            f"(best estimate {max(o['total'], 0):.0f})",
            f"Extra profit for you: {fmt_inr(p['low'], True)} to {fmt_inr(p['high'], True)} "
            f"(best estimate {fmt_inr(p['total'], True)})",
            f"How we know: 1 in {one_in} eligible customers did not see the offer, and we compare the two groups.",
            VERDICT_SENTENCES[m.get("verdict_code", "wait")],
            "Open the Offers tab in the partner app to keep, change or stop it.",
        ]
    )
