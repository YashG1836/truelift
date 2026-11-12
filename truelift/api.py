"""TrueLift service: the four hooks Zomato's offer flow would call, plus the demo screens.

Run:  .venv/bin/uvicorn truelift.api:app --port 8000   then open http://localhost:8000

Hooks (what Zomato's systems call)
  POST /api/quote                   offer-creation screen: forecast + better version (before the OTP)
  POST /api/offers                  create an offer awaiting the owner's OTP
  POST /api/offers/{id}/approve     owner enters the OTP: consent is recorded with the forecast shown
  GET  /api/serve                   menu opened: show the discount to this customer or not (<10 ms)
  POST /api/offers/{id}/run_week    demo only: simulate the next week of the offer
  GET  /api/offers/{id}             weekly measurement, WhatsApp summary, itemised payout
  POST /api/offers/{id}/decision    keep / stop (renewal after the consent period needs a new OTP)
Demo data comes from the simulator (synthetic customers, real Bengaluru restaurant listings).
"""
from __future__ import annotations

import copy
import json
import pickle
import secrets
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .economics import Terms, weekly_example
from .engine import Design, Engine, weekly_message
from .sim import (Config, Market, build_history, display_name, recent_visits, restaurant_baskets,
                  status_quo_policy)

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).resolve().parent / "static"
CONSENT_WEEKS = 4
DEMO_RESTAURANT = 233


class DesignIn(BaseModel):
    discount: float = Field(60, ge=0, le=500)
    min_order: float = Field(0, ge=0, le=5000)
    audience: str = Field("all", pattern="^(all|new_to_restaurant|lapsed|targeted)$")
    offpeak_only: bool = False
    reward: float = Field(0, ge=0, le=200)
    zomato_share: float = Field(0, ge=0, le=1)


class QuoteIn(BaseModel):
    restaurant_id: int
    design: DesignIn


class OtpIn(BaseModel):
    otp: str


class DecisionIn(BaseModel):
    action: str = Field(pattern="^(keep|stop)$")


@dataclass
class Offer:
    id: int
    restaurant_id: int
    design: Design
    quote: dict
    otp: str
    status: str = "awaiting_otp"  # awaiting_otp | active | paused | stopped | consent_expired
    consent: dict | None = None
    weeks: list = field(default_factory=list)
    rows: list = field(default_factory=list)


class State:
    """Everything the demo needs, rebuilt deterministically at start-up (a few seconds)."""

    def __init__(self):
        art = pickle.load(open(ROOT / "data/processed/model.pkl", "rb"))
        cfg = Config(**{k: tuple(v) if isinstance(v, list) else v for k, v in art["config"].items()})
        self.R = pd.read_csv(ROOT / "data/processed/restaurants.csv")
        self.market = Market(self.R, cfg, Terms())
        self.hist, train = build_history(self.market)
        n = self.market.n_rest
        self.baskets = restaurant_baskets(train, n)
        self.engine = Engine(art["model"], Terms(), art["sigma_rel"], art["sigma_orders"],
                             topup_value=art["topup_value"])
        visits = recent_visits(self.market, self.hist)
        self.visits = dict(tuple(visits.groupby("rest")))
        # demo default: Burger King, Jayanagar (₹420 average order, close to the Round 1 ₹400 example)
        self.demo_restaurant = DEMO_RESTAURANT if DEMO_RESTAURANT in set(self.R["restaurant_id"]) else int(art["demo_restaurant"])
        self.background = status_quo_policy(self.market, np.random.default_rng(4242), name="market")
        # the demo restaurant starts without an offer; its competitors keep today's offers
        self.background.discount[self.demo_restaurant] = 0.0
        self.offers: dict[int, Offer] = {}
        self.feature_cache: dict[int, dict] = {}
        self.calls: list[dict] = []

    def x_for(self, rid: int) -> pd.DataFrame:
        if rid not in self.visits:
            raise HTTPException(404, "restaurant has no recent visits")
        return self.visits[rid].drop(columns=["rest", "cust"])

    def week_inputs(self, w: int):
        if w not in self.feature_cache:
            occ = self.market.occasions(w)
            self.feature_cache[w] = (occ, self.market.flat_features(self.hist, occ))
        return self.feature_cache[w]


STATE: State | None = None
app = FastAPI(title="TrueLift", version="1.0")


def st() -> State:
    global STATE
    if STATE is None:
        STATE = State()
    return STATE


def logged(name: str, t0: float, **info):
    s = st()
    s.calls.append({"hook": name, "ms": round((time.perf_counter() - t0) * 1000, 1), **info})
    s.calls[:] = s.calls[-30:]


def restaurant_card(s: State, rid: int) -> dict:
    r = s.R.loc[rid]
    x = s.visits.get(rid)
    h = s.hist
    orders_4w = sum(h.pair_orders[-4:])[:, int(s.market.R.loc[rid, "local"])]
    loc = s.market.R.loc[rid, "loc"]
    in_loc = s.market.c_loc == loc
    o = orders_4w[in_loc]
    regular_orders = o[o >= 3].sum()
    return {
        "restaurant_id": rid, "name": display_name(r), "locality": r["locality"], "cuisines": r["cuisines"],
        "rating": float(r["rating"]), "aov": float(s.market.aov[rid]),
        "orders_per_week": round(float(o.sum()) / 4, 1),
        "regular_customers": int((o >= 3).sum()),
        "regulars_share_of_orders": round(float(regular_orders / max(o.sum(), 1)), 3),
        "menu_visits_per_week": round(len(x) / 2) if x is not None else 0,
    }


@app.get("/api/restaurants")
def restaurants():
    s = st()
    cards = [restaurant_card(s, int(r)) for r in s.R["restaurant_id"]]
    return {"demo_restaurant": s.demo_restaurant, "restaurants": cards}


@app.get("/api/restaurants/{rid}")
def restaurant(rid: int):
    s = st()
    if rid not in set(s.R["restaurant_id"]):
        raise HTTPException(404, "unknown restaurant")
    return restaurant_card(s, rid)


@app.post("/api/quote")
def quote(q: QuoteIn):
    """Hook 1: offer creation. Forecast for the owner's design and the best alternative."""
    t0 = time.perf_counter()
    s = st()
    d = Design(**q.design.model_dump())
    rid = q.restaurant_id
    owner, best = s.engine.best_design(s.x_for(rid), d, float(s.market.aov[rid]), s.baskets[rid], weeks=2)
    better = best if best["profit_change"] > owner["profit_change"] + 50 else None
    logged("quote", t0, restaurant=rid)
    return clean({"owner": owner, "better": better, "designs_compared": best["designs_compared"],
                  "consent_weeks": CONSENT_WEEKS})


@app.post("/api/offers")
def create_offer(q: QuoteIn):
    s = st()
    d = Design(**q.design.model_dump())
    rid = q.restaurant_id
    qt = s.engine.quote(s.x_for(rid), d, float(s.market.aov[rid]), s.baskets[rid], weeks=2)
    oid = len(s.offers) + 1
    s.offers[oid] = Offer(oid, rid, d, qt, otp=f"{secrets.randbelow(9000) + 1000}")
    return {"offer_id": oid, "status": "awaiting_otp", "quote": clean(qt),
            "otp_sent_to": "owner's registered phone", "demo_otp": s.offers[oid].otp}


@app.post("/api/offers/{oid}/approve")
def approve(oid: int, body: OtpIn):
    """The owner's consent, recorded with exactly what they were shown (auditable)."""
    s = st()
    off = get(oid)
    if off.status != "awaiting_otp":
        raise HTTPException(409, f"offer is {off.status}")
    if body.otp.strip() != off.otp:
        raise HTTPException(403, "Wrong OTP. Check the code and try again.")
    off.status = "active"
    off.consent = {"approved_at": time.strftime("%Y-%m-%d %H:%M"), "design": asdict(off.design),
                   "label": off.design.label(), "forecast_shown": off.quote,
                   "valid_for_weeks": CONSENT_WEEKS, "who_pays": who_pays(off.design)}
    return offer_view(off)


def who_pays(d: Design) -> str:
    if d.zomato_share > 0:
        return (f"You pay the discount, except for customers new to Zomato, where Zomato pays "
                f"{d.zomato_share:.0%}. Brand Pack rewards are paid by you.")
    return "You pay the discount and any Brand Pack rewards. Nothing is deducted without this approval."


@app.get("/api/serve")
def serve(restaurant_id: int, customer_id: int, slot: int = 2):
    """Hook 2: a customer opens this restaurant's menu. Show the discount or not."""
    t0 = time.perf_counter()
    s = st()
    active = [o for o in s.offers.values() if o.restaurant_id == restaurant_id and o.status == "active"]
    if not active:
        return {"show_offer": False, "reason": "no active offer"}
    off = active[-1]
    x = customer_features(s, customer_id, restaurant_id, slot)
    out = s.engine.serve(x, off.design, float(s.market.aov[restaurant_id]), s.baskets[restaurant_id],
                         customer_id, off.id)
    logged("serve", t0, restaurant=restaurant_id, customer=customer_id, show=out["show_offer"])
    out["latency_ms"] = s.calls[-1]["ms"]
    return clean(out)


def customer_features(s: State, cid: int, rid: int, slot: int) -> pd.DataFrame:
    local = int(s.market.R.loc[rid, "local"])
    if s.market.c_loc[cid] != s.market.R.loc[rid, "loc"]:
        raise HTTPException(400, "customer is not in this restaurant's locality")
    f = s.market.features(s.hist, np.array([cid]), np.array([local]), np.array([rid]))
    f.update(slot=np.array([slot]), reward=np.array([0.0]))
    return pd.DataFrame(f)


@app.post("/api/customers")
def sample_customers(q: QuoteIn):
    """A few of this restaurant's recent visitors (synthetic people) and what TrueLift does for each."""
    s = st()
    rid = q.restaurant_id
    x = s.visits.get(rid)
    if x is None:
        raise HTTPException(404, "no visitors")
    x = x.drop_duplicates("cust")
    groups = [("regular", x[x["cr_orders_4w"] >= 3]), ("stopped ordering", x[(x["cr_orders_all"] > 0) & (x["cr_weeks_since"] >= 4)]),
              ("new to you", x[(x["cr_orders_all"] == 0) & (x["c_new_to_zomato"] == 0)]),
              ("new to Zomato", x[x["c_new_to_zomato"] == 1])]
    active = [o for o in s.offers.values() if o.restaurant_id == rid and o.status == "active"]
    d = active[-1].design if active else Design(**q.design.model_dump())
    oid = active[-1].id if active else 0
    out = []
    for label, g in groups:
        for _, row in g.head(2).iterrows():
            cid = int(row["cust"])
            item = {"customer_id": cid, "group": label, "orders_here_4w": int(row["cr_orders_4w"]),
                    "orders_here_ever": int(row["cr_orders_all"]), "zomato_orders_per_week": round(row["c_orders_pw"], 2),
                    "share_of_orders_with_discount": round(row["c_disc_share"], 2),
                    "weeks_since_last_order_here": int(row["cr_weeks_since"])}
            xr = customer_features(s, cid, rid, 2)
            item["decision"] = s.engine.serve(xr, d, float(s.market.aov[rid]), s.baskets[rid], cid, oid)
            out.append(item)
    return clean({"customers": out, "design": asdict(d), "label": d.label()})


@app.post("/api/offers/{oid}/run_week")
def run_week(oid: int):
    """Demo: simulate the next week for this restaurant (competitors keep today's offers)."""
    s = st()
    off = get(oid)
    if off.status != "active":
        raise HTTPException(409, f"offer is {off.status}")
    w = len(off.weeks) + 1
    occ, feats = s.week_inputs(w)
    rid, d = off.restaurant_id, off.design
    # competitors keep today's offers; this restaurant runs TrueLift with its 10% holdout
    # (in the simulation the holdout also trims competitors' reach slightly; it doesn't matter here)
    pol = copy.deepcopy(s.background)
    for attr in ("discount", "min_order", "offpeak_only", "zomato_share", "reward", "audience"):
        getattr(pol, attr)[rid] = getattr(d, attr)
    pol.holdout = s.engine.holdout
    mixes = np.zeros((s.market.n_rest, 4))
    mixes[rid] = s.engine.mix(s.baskets[rid], d, float(s.market.aov[rid]))
    pol.scorer = s.engine.targeting_scorer(mixes)  # only this restaurant's offer is targeted
    res = s.market.run_week(occ, pol, feats, salt=1000 + oid, truth=True)
    mine = res["rest"] == rid
    df = pd.DataFrame({k: v[mine] for k, v in res.items() if isinstance(v, np.ndarray) and len(v) == len(mine)})
    off.rows.append(df[df["eligible"]])
    rows = pd.concat(off.rows, ignore_index=True)
    aov = float(s.market.aov[rid])
    v = s.engine.design_values(rows.reset_index(drop=True), d, aov, s.baskets[rid])
    m = s.engine.measure(rows, aov, float(v["gain"].mean()), float((v["p1"] - v["p0"]).mean()),
                         v["p0"] * v["profit0"], v["p0"])
    sh = rows["shown"].to_numpy()
    truth = {"extra_orders": float((rows["p"] - rows["p_cf"]).to_numpy()[sh].sum()),
             "extra_profit": float((rows["p"] * rows["profit"] - rows["p_cf"] * rows["profit_cf"]).to_numpy()[sh].sum())}
    ch = df[df["chosen"]]
    reward = float(ch["reward"].sum())
    payout = {
        "orders": int(len(ch)), "gross_sales": round(float(ch["basket"].sum())),
        "discount_paid_by_you": round(float(ch["restaurant_funded"].sum()) - reward),
        "brand_pack_rewards_paid_by_you": round(reward),
        "discount_paid_by_zomato": round(float(ch["zomato_funded"].sum())),
        "commission_25pct": round(float(ch["commission"].sum())),
        "gst_on_commission_18pct": round(0.18 * float(ch["commission"].sum())),
    }
    payout["net_payout"] = (payout["gross_sales"] - payout["discount_paid_by_you"] - payout["brand_pack_rewards_paid_by_you"]
                            - payout["commission_25pct"] - payout["gst_on_commission_18pct"])
    name = display_name(s.R.loc[rid])
    week = {"week": w, "measurement": clean(m), "simulator_truth": truth, "payout": payout,
            "whatsapp": weekly_message(name, w, m, d)}
    off.weeks.append(week)
    if w >= 2 and m["verdict"].startswith("losing"):
        off.status = "paused"
    elif w >= CONSENT_WEEKS:
        off.status = "consent_expired"
    return offer_view(off)


def clean(o):
    """Make engine results JSON-safe: numpy scalars to Python, infinities to None."""
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (bool, np.bool_)):
        return bool(o)
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else round(float(o), 3)
    if isinstance(o, np.integer):
        return int(o)
    return o


def offer_view(off: Offer) -> dict:
    return clean({"offer_id": off.id, "restaurant_id": off.restaurant_id, "status": off.status,
            "design": asdict(off.design), "label": off.design.label(), "quote": off.quote,
            "consent": off.consent, "weeks": off.weeks, "who_pays": who_pays(off.design)})


def get(oid: int) -> Offer:
    off = st().offers.get(oid)
    if off is None:
        raise HTTPException(404, "no such offer")
    return off


@app.get("/api/offers/{oid}")
def get_offer(oid: int):
    return offer_view(get(oid))


@app.post("/api/offers/{oid}/decision")
def decision(oid: int, body: DecisionIn):
    off = get(oid)
    if body.action == "stop":
        off.status = "stopped"
    elif off.status == "active":
        pass  # keep running
    else:
        raise HTTPException(409, "renewing a paused or expired offer needs a fresh quote and OTP")
    return offer_view(off)


@app.get("/api/calls")
def calls():
    return {"calls": st().calls[::-1]}


@app.get("/api/example")
def example():
    return weekly_example(Terms())


@app.get("/api/evidence")
def evidence():
    p = ROOT / "reports/evaluation.json"
    if not p.exists():
        raise HTTPException(404, "run scripts/run_pipeline.py first")
    out = json.loads(p.read_text())
    real = ROOT / "reports/uplift_validation_criteo.json"  # check on real randomised data
    if real.exists():
        out["real_data_criteo"] = json.loads(real.read_text())
    return out


@app.post("/api/reset")
def reset():
    s = st()
    s.offers.clear()
    s.calls.clear()
    return {"ok": True}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
