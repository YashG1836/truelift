"""Synthetic Bengaluru food-delivery market where the true effect of every discount is known.

Why: no public dataset has restaurant offers with rupee outcomes and a random control group.
In this market we can compute what would have happened without each discount, so we can check
whether TrueLift's estimates are right and compare it with today's blanket discounts.

One ordering occasion (a customer opens the app wanting food):
  - the customer looks at K menus from their locality (Eternal: users browse ~12 menus per order);
  - they pick the option with the highest utility: one of those K restaurants, Swiggy, or nothing;
  - utility(restaurant r) = base(type) + favourite bonus + 0.8 x (rating - 3.9) + taste(c, r)
                            + price_sensitivity(type) x saving / 100
  - utility(Swiggy)       = swiggy_base(type) + price_sensitivity(type) x swiggy_saving / 100
  - utility(nothing)      = 0
Choice probabilities follow the logit (softmax) rule. Expected values give the truth; sampled
choices (Gumbel-max with fixed random draws, identical across policies) give what Zomato observes.

Customer types are hidden from every model. Models only see order history, like Zomato would.
Restaurants (names, localities, ratings, cost for two) come from the public Zomato Bangalore data.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .assignment import in_control_group, stable_uniform  # noqa: F401  (stable_uniform re-exported)
from .economics import Terms, split
from .features import HistoryFeatures

TYPES = ("loyal", "casual", "deal_seeker", "infrequent")
SLOTS = ("lunch", "3-6 pm", "dinner")


def display_name(r) -> str:
    """How a restaurant is shown: its real public listing name. Its orders and profits here are
    simulated, and every screen that shows numbers says so."""
    return str(r["name"])


@dataclass(frozen=True)
class Config:
    customers_per_locality: int = 5000
    type_share: tuple = (0.25, 0.40, 0.20, 0.15)
    occasions_per_week: tuple = (2.0, 0.9, 1.0, 0.5)
    base_utility: tuple = (-2.3, -2.5, -3.3, -3.0)
    favourite_bonus: tuple = (2.8, 1.4, 0.3, 0.0)
    price_sensitivity: tuple = (0.45, 1.2, 2.6, 1.6)  # utility per ₹100 saved
    swiggy_base: tuple = (-1.1, -0.7, -0.1, -1.3)
    swiggy_saving: float = 40.0  # typical saving on Swiggy at a similar restaurant
    taste_sd: float = 1.0
    menus_per_occasion: int = 8
    topup_value: float = 0.5  # share of a top-up (to reach a minimum order) the customer values
    slot_share: tuple = (0.35, 0.15, 0.50)
    joiner_share: float = 0.08  # customers who first open Zomato in the evaluation period
    aov_factor: float = 0.7  # average order value = 0.7 x the listed cost for two
    seed: int = 7


@dataclass
class Policy:
    """What every restaurant offers in one world. Arrays have one entry per restaurant."""

    discount: np.ndarray  # ₹ off; 0 means no offer
    min_order: np.ndarray  # ₹; 0 means none
    offpeak_only: np.ndarray  # bool: offer valid only 3-6 pm
    zomato_share: np.ndarray  # fraction of the discount Zomato funds
    reward: np.ndarray  # Brand Pack ₹ per order for the restaurant's regulars (3+ orders in 4 weeks)
    audience: np.ndarray  # "all", "new_to_restaurant", "lapsed", "targeted"
    holdout: float = 0.10  # random share of eligible customers who don't see the offer
    scorer: object = None  # for "targeted": callable(features, policy) -> bool array
    name: str = ""
    # When set (one id per restaurant), the holdout is the shared (customer, offer) assignment that
    # serving uses, so the simulated weeks hold out exactly the customers `serve` holds out.
    # Evaluation policies leave it unset and keep their own salts.
    offer_id: np.ndarray | None = None

    @classmethod
    def none(cls, n: int, name: str = "no offer") -> Policy:
        return cls(
            np.zeros(n),
            np.zeros(n),
            np.zeros(n, bool),
            np.zeros(n),
            np.zeros(n),
            np.array(["all"] * n, dtype=object),
            0.0,
            None,
            name,
        )


@dataclass
class History:
    """What Zomato can see: weekly order and visit counts. Kept per week to build windows."""

    pair_orders: list = field(default_factory=list)  # per week: (customers, 50) int16
    pair_visits: list = field(default_factory=list)
    cust_orders: list = field(default_factory=list)  # per week: (customers,)
    cust_disc_orders: list = field(default_factory=list)
    cust_sessions: list = field(default_factory=list)
    weeks: list = field(default_factory=list)  # week number of each entry, in order

    def before(self, week: int) -> History:
        """The history as it stood when `week` began: only the weeks before it (no look-ahead)."""
        k = sum(1 for w in self.weeks if w < week)
        return History(
            self.pair_orders[:k],
            self.pair_visits[:k],
            self.cust_orders[:k],
            self.cust_disc_orders[:k],
            self.cust_sessions[:k],
            self.weeks[:k],
        )


class Market:
    def __init__(self, restaurants: pd.DataFrame, cfg: Config = Config(), terms: Terms = Terms()):
        self.cfg, self.terms = cfg, terms
        r = restaurants.sort_values("restaurant_id").reset_index(drop=True).copy()
        # restaurant_id is used as an array index and localities as equal blocks: check, don't assume
        if not np.array_equal(r["restaurant_id"].to_numpy(), np.arange(len(r))):
            raise ValueError("restaurant_id must run 0, 1, ..., n-1 with no gaps")
        sizes = r.groupby("locality", sort=False).size()
        if sizes.nunique() != 1:
            raise ValueError(f"every locality needs the same number of restaurants; got {sizes.to_dict()}")
        self.localities = list(dict.fromkeys(r["locality"]))
        r["loc"] = r["locality"].map({name: i for i, name in enumerate(self.localities)})
        r["local"] = r.groupby("loc").cumcount()
        r["aov"] = (cfg.aov_factor * r["cost_for_two"]).clip(150, 1000).round(-1)
        r["pop"] = np.sqrt(r["votes"].astype(float))
        self.R = r
        self.n_rest = len(r)
        self.per_loc = int(r.groupby("loc").size().iloc[0])
        self.rest_global = np.zeros((len(self.localities), self.per_loc), int)
        self.rest_global[r["loc"].to_numpy(), r["local"].to_numpy()] = r["restaurant_id"].to_numpy()

        rng = np.random.default_rng(cfg.seed)
        n = cfg.customers_per_locality * len(self.localities)
        self.n_cust = n
        self.c_loc = np.repeat(np.arange(len(self.localities)), cfg.customers_per_locality)
        self.c_type = rng.choice(len(TYPES), n, p=cfg.type_share)
        self.c_joiner = rng.random(n) < cfg.joiner_share
        w = r["pop"].to_numpy().reshape(len(self.localities), self.per_loc)
        self.pop_local = w / w.sum(1, keepdims=True)
        self.c_fav = np.array([rng.choice(self.per_loc, p=self.pop_local[loc]) for loc in self.c_loc])
        self.taste = rng.normal(0, cfg.taste_sd, (n, self.per_loc))
        self.bmult = rng.lognormal(0, 0.2, (n, self.per_loc))
        self.aov = r["aov"].to_numpy(float)
        self.rating = r["rating"].to_numpy(float)

    # ---------- one week of occasions (random draws fixed by the week number) ----------
    def occasions(self, week: int) -> dict:
        cfg = self.cfg
        rng = np.random.default_rng(cfg.seed * 1000 + week + 500)
        active = ~self.c_joiner if week < 0 else np.ones(self.n_cust, bool)
        rate = np.array(cfg.occasions_per_week)[self.c_type] * active
        cust = np.repeat(np.arange(self.n_cust), rng.poisson(rate))
        m, k = len(cust), cfg.menus_per_occasion
        slot = rng.choice(3, m, p=cfg.slot_share)
        loc = self.c_loc[cust]
        g = np.log(self.pop_local[loc]) + rng.gumbel(size=(m, self.per_loc))
        local = np.argsort(-g, axis=1)[:, :k]
        # loyal customers always see their favourite; casual ones half the time
        fav = self.c_fav[cust]
        has_fav = (local == fav[:, None]).any(1)
        force = (~has_fav) & ((self.c_type[cust] == 0) | ((self.c_type[cust] == 1) & (rng.random(m) < 0.5)))
        local[force, k - 1] = fav[force]
        return {
            "week": week,
            "cust": cust,
            "slot": slot,
            "local": local,
            "rest": self.rest_global[loc[:, None], local],
            "gumbel": rng.gumbel(size=(m, k + 2)),
        }

    # ---------- observable features at a snapshot ----------
    def features(self, hist: History, cust: np.ndarray, local: np.ndarray, rest: np.ndarray) -> dict:
        """Features for (customer, restaurant) exposures, computed only from observed history."""
        return HistoryFeatures(self, hist).for_exposures(cust, local, rest)

    # ---------- run one week under a policy ----------
    def run_week(self, occ: dict, policy: Policy, feats: dict, salt: int = 0, truth: bool = True) -> dict:
        """Returns one row per exposure (customer saw a restaurant's menu) with outcomes.

        feats: features for the flattened exposures (from `features` at the snapshot).
        """
        cfg, t = self.cfg, self.terms
        cust = occ["cust"]
        m, k = occ["rest"].shape
        typ = self.c_type[cust]
        rest = occ["rest"].ravel()
        c = np.repeat(cust, k)
        slot = np.repeat(occ["slot"], k)
        local = occ["local"].ravel()
        basket0 = self.aov[rest] * self.bmult[c, local]

        # who is eligible for the discount, and who is held out at random
        aud = policy.audience[rest]
        elig = policy.discount[rest] > 0
        elig &= ~policy.offpeak_only[rest] | (slot == 1)
        rule = np.ones_like(elig)
        rule[aud == "new_to_restaurant"] = (feats["cr_orders_all"] == 0)[aud == "new_to_restaurant"]
        lapsed = (feats["cr_orders_all"] > 0) & (feats["cr_weeks_since"] >= 4)
        rule[aud == "lapsed"] = lapsed[aud == "lapsed"]
        if policy.scorer is not None and (aud == "targeted").any():
            tg = aud == "targeted"
            rule[tg] = policy.scorer({**feats, "rest": rest, "slot": slot, "cust": c}, policy, tg)
        elig &= rule
        if policy.offer_id is not None:  # the same (customer, offer) assignment serving uses
            hold = elig & in_control_group(c, policy.offer_id[rest], policy.holdout)
        else:
            hold = elig & (stable_uniform(c, rest, salt + 1) < policy.holdout)
        shown = elig & ~hold

        mov = policy.min_order[rest]
        topup = np.maximum(0.0, mov - basket0)
        eff = np.where(shown, policy.discount[rest] - (1 - cfg.topup_value) * topup, 0.0)
        takes = shown & (eff > 0)
        basket = np.where(takes, np.maximum(basket0, mov), basket0)
        disc = np.where(takes, policy.discount[rest], 0.0)
        regular = feats["cr_orders_4w"] >= 3
        reward = np.where(regular, policy.reward[rest], 0.0)
        saving = np.where(takes, eff, 0.0) + reward
        # Zomato co-funds only customers new to Zomato (new accounts), as the engine and every
        # document say; it used to pay for every redemption (audit TL-003)
        zshare = np.where(takes & (feats["c_new_account"] == 1), policy.zomato_share[rest], 0.0)
        # Brand Pack reward is a restaurant-funded discount; Zomato share applies to the offer only
        total_disc = disc + reward
        zs_eff = np.where(total_disc > 0, zshare * disc / np.maximum(total_disc, 1e-9), 0.0)

        sens = np.array(cfg.price_sensitivity)[typ]
        u_r = (
            np.array(cfg.base_utility)[typ][:, None]
            + np.array(cfg.favourite_bonus)[typ][:, None] * (occ["local"] == self.c_fav[cust][:, None])
            + 0.8 * (self.rating[occ["rest"]] - 3.9)
            + self.taste[cust[:, None], occ["local"]]
            + sens[:, None] * saving.reshape(m, k) / 100.0
        )
        u_s = np.array(cfg.swiggy_base)[typ] + sens * cfg.swiggy_saving / 100.0
        u = np.concatenate([u_r, u_s[:, None], np.zeros((m, 1))], axis=1)
        e = np.exp(u - u.max(1, keepdims=True))
        p = e / e.sum(1, keepdims=True)
        choice = np.argmax(u + occ["gumbel"], axis=1)
        chosen = (choice[:, None] == np.arange(k)[None, :]).ravel()

        money = split(basket, total_disc, zs_eff, t)
        out = {
            "week": np.full(m * k, occ["week"]),
            "occ": np.repeat(np.arange(m), k),
            "cust": c,
            "rest": rest,
            "local": local,
            "slot": slot,
            "type": np.repeat(typ, k),
            "eligible": elig,
            "holdout": hold,
            "shown": shown,
            "takes": takes,
            "regular": regular,
            "discount": disc,
            "reward": reward,
            "saving": saving,
            "basket": basket,
            "p": p[:, :k].ravel(),
            "chosen": chosen,
            "profit": money["restaurant_profit"],
            "commission": money["commission"],
            "zomato_funded": money["zomato_funded"],
            "restaurant_funded": money["restaurant_funded"],
            "zomato_contribution": money["zomato_contribution"],
            "p_swiggy": np.repeat(p[:, k], k),
            "p_none": np.repeat(p[:, k + 1], k),
            "chosen_swiggy": np.repeat(choice == k, k),
        }
        if truth:
            # counterfactual: this exposure's offer removed (Brand Pack reward kept), others unchanged
            s_cf = reward.reshape(m, k)
            u_cf_self = u_r - sens[:, None] * (saving.reshape(m, k) - s_cf) / 100.0
            e_self = np.exp(u_r - u.max(1, keepdims=True))
            e_cf = np.exp(u_cf_self - u.max(1, keepdims=True))
            denom = e.sum(1, keepdims=True)
            denom_cf = denom - e_self + e_cf
            p_cf = (e_cf / denom_cf).ravel()
            zomato_now = e[:, :k].sum(1, keepdims=True) / denom
            zomato_cf = (e[:, :k].sum(1, keepdims=True) - e_self + e_cf) / denom_cf
            money_cf = split(basket0, reward, np.zeros_like(reward), t)
            out.update(
                {
                    "p_cf": p_cf,
                    "basket_cf": basket0,
                    "profit_cf": money_cf["restaurant_profit"],
                    "commission_cf": money_cf["commission"],
                    "zomato_contribution_cf": money_cf["zomato_contribution"],
                    # change in this customer's Zomato orders on this occasion caused by this offer
                    "platform_lift": (zomato_now - zomato_cf).ravel(),
                    "p_swiggy_cf": (e[:, k : k + 1] / denom_cf).ravel(),
                }
            )
        for name, arr in feats.items():
            out[name] = arr
        return out

    def record(self, hist: History, res: dict) -> None:
        """Add one simulated week's observed outcomes to the history."""
        n, L = self.n_cust, self.per_loc
        po = np.zeros((n, L), np.int16)
        pv = np.zeros((n, L), np.int16)
        np.add.at(pv, (res["cust"], res["local"]), 1)
        ch = res["chosen"]
        np.add.at(po, (res["cust"][ch], res["local"][ch]), 1)
        co = np.bincount(res["cust"][ch], minlength=n)
        cd = np.bincount(res["cust"][ch & res["takes"]], minlength=n)
        occ_c = res["cust"][np.r_[True, res["occ"][1:] != res["occ"][:-1]]]
        cs = np.bincount(occ_c, minlength=n)
        hist.pair_orders.append(po)
        hist.pair_visits.append(pv)
        hist.cust_orders.append(co)
        hist.cust_disc_orders.append(cd)
        hist.cust_sessions.append(cs)
        hist.weeks.append(int(res["week"][0]) if len(res["week"]) else (hist.weeks[-1] + 1 if hist.weeks else 0))

    def flat_features(self, hist: History, occ: dict) -> dict:
        k = occ["rest"].shape[1]
        return self.features(hist, np.repeat(occ["cust"], k), occ["local"].ravel(), occ["rest"].ravel())


def status_quo_policy(
    market: Market,
    rng: np.random.Generator,
    holdout: float = 0.0,
    share_active: float = 0.4,
    explore: bool = False,
    name: str = "",
) -> Policy:
    """Today's market: a share of restaurants run blanket flat discounts.

    explore=True varies designs (depth, minimum order, 3-6 pm, audience, Brand Pack) at random and
    keeps a random holdout: the data TrueLift's shadow phase would collect.
    """
    n = market.n_rest
    active = rng.random(n) < share_active
    depth = rng.choice([40.0, 60.0, 80.0, 100.0], n) if explore else rng.choice([40.0, 50.0, 60.0, 80.0], n)
    discount = np.where(active, depth, 0.0)
    use_mov = rng.random(n) < 0.4
    mov = np.where(active & use_mov, np.round(market.aov * rng.choice([1.0, 1.15, 1.3], n) / 50) * 50 - 1, 0.0)
    mov = np.maximum(mov, 0.0)
    offpeak = active & (rng.random(n) < (0.25 if explore else 0.0))
    reward = np.where(rng.random(n) < (0.3 if explore else 0.0), rng.choice([15.0, 25.0], n), 0.0)
    aud = np.array(["all"] * n, dtype=object)
    if explore:
        aud = rng.choice(np.array(["all", "all", "new_to_restaurant", "lapsed"], dtype=object), n)
    return Policy(discount, mov, offpeak, np.zeros(n), reward, aud, holdout, None, name)


def build_history(market: Market, weeks_quo: int = 8, weeks_explore: int = 4, light: bool = False):
    """Simulate history: `weeks_quo` weeks of today's market, then `weeks_explore` weeks of
    TrueLift's shadow phase (random designs, 10% random holdout). Returns (history, training rows).

    Every week's features come from the history before that week (rolling), and the eight
    status-quo weeks give the first shadow week a full look-back, so training rows have exactly the
    windows that quoting, serving and evaluation use (audit TL-007).

    light=True is for the service: the same history, but instead of the million-row training
    table it keeps only the orders `restaurant_baskets` needs (a fraction of the memory).
    """
    hist = History()
    rng = np.random.default_rng(market.cfg.seed + 99)
    start = -(weeks_quo + weeks_explore)
    for w in range(start, start + weeks_quo):
        occ = market.occasions(w)
        pol = status_quo_policy(market, rng, name="status quo")
        res = market.run_week(occ, pol, market.flat_features(hist, occ), salt=1, truth=False)
        market.record(hist, res)
    train = []
    for w in range(start + weeks_quo, 0):
        occ = market.occasions(w)
        pol = status_quo_policy(market, rng, holdout=0.10, share_active=0.6, explore=True, name="shadow")
        # holdout salt is fixed for the whole phase: a held-out customer stays held out
        res = market.run_week(occ, pol, market.flat_features(hist, occ), salt=2, truth=not light)
        if light:
            keep = res["chosen"] & ~res["shown"] & (res["reward"] == 0)
            train.append(
                pd.DataFrame(
                    {
                        "rest": res["rest"][keep],
                        "basket": res["basket"][keep],
                        "chosen": True,
                        "shown": False,
                        "reward": 0.0,
                    }
                )
            )
            market.record(hist, res)
            continue
        for key in ("min_order", "offpeak_only"):
            res[key] = getattr(pol, key)[res["rest"]]
        res["offer_discount"] = pol.discount[res["rest"]]
        res["offer_reward"] = pol.reward[res["rest"]]
        res["audience"] = pol.audience[res["rest"]]
        train.append(pd.DataFrame(res))
        market.record(hist, res)
    return hist, pd.concat(train, ignore_index=True)


def restaurant_baskets(train: pd.DataFrame, n: int) -> list[np.ndarray]:
    """Observed order values of each restaurant's orders from customers who were not shown an offer
    (what Zomato sees). Customers shown a minimum-order offer are excluded: those who skipped the
    offer are the ones with small baskets, so including them would bias the average down."""
    full = train[train["chosen"] & ~train["shown"] & (train["reward"] == 0)]
    g = full.groupby("rest")["basket"].apply(np.asarray)
    return [g.get(r, np.array([])) for r in range(n)]


def recent_visits(market: Market, hist, weeks=(-2, -1)) -> pd.DataFrame:
    """Each restaurant's menu visits in the last two weeks (the quote's input), each with the
    features it had when it happened: the history before that week, never the visit's own outcome
    (audit TL-006)."""
    parts = []
    for w in weeks:
        occ = market.occasions(w)
        k = occ["rest"].shape[1]
        f = market.flat_features(hist.before(w), occ)
        f.update(
            rest=occ["rest"].ravel(),
            slot=np.repeat(occ["slot"], k),
            cust=np.repeat(occ["cust"], k),
            week=np.full(len(f["r_aov"]), w),
            reward=np.zeros(len(f["r_aov"])),
        )
        parts.append(pd.DataFrame(f))
    return pd.concat(parts, ignore_index=True)
