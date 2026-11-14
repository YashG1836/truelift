"""What the service holds: the market, the model, cached restaurant cards, and the demo sessions.

Start-up never rebuilds the million-row training table. The history the demo needs is simulated
once (deterministically) and cached in `serving_<key>.npz`, so later starts only load arrays
(audit TL-014). Each visitor's offers live in their own session, ids come from one locked counter
and are never reused (TL-008).
"""

from __future__ import annotations

import hashlib
import inspect
import itertools
import json
import os
import tempfile
import threading
import time
from collections import deque
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import features as features_module
from . import sim as sim_module
from .economics import Terms
from .engine import DecisionTable, Design, Engine, design_options
from .features import HistoryFeatures
from .model import load_bundle
from .settings import Settings
from .sim import (
    Config,
    History,
    Market,
    build_history,
    display_name,
    recent_visits,
    restaurant_baskets,
    status_quo_policy,
)
from .store import Store

OTP_TTL_SECONDS = 600
OTP_MAX_ATTEMPTS = 5


@dataclass
class Offer:
    id: int
    session: str
    restaurant_id: int
    design: Design
    quote: dict
    otp: str
    created_at: float = field(default_factory=time.time)
    status: str = "awaiting_otp"  # awaiting_otp | active | paused | stopped | consent_expired | replaced | otp_expired
    otp_attempts: int = 0
    consent: dict | None = None
    weeks: list = field(default_factory=list)
    table: DecisionTable | None = None
    replaced_by: int | None = None
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


@dataclass
class Session:
    id: str
    offers: dict = field(default_factory=dict)  # offer id -> Offer
    calls: deque = field(default_factory=lambda: deque(maxlen=30))
    idempotency: dict = field(default_factory=dict)  # Idempotency-Key -> stored response
    last_seen: float = field(default_factory=time.time)


# ---------------------------------------------------------------- serving cache
def serving_key(cfg: Config) -> str:
    """Changes whenever the market's configuration or the simulator's code changes."""
    src = inspect.getsource(sim_module) + inspect.getsource(features_module)
    raw = json.dumps(asdict(cfg), sort_keys=True, default=str) + src
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _save_serving(path: Path, hist: History, baskets: list) -> None:
    lengths = np.array([len(b) for b in baskets], dtype=np.int64)
    flat = np.concatenate([np.asarray(b, float) for b in baskets]) if len(baskets) else np.zeros(0)
    arrays = {
        "pair_orders": np.stack(hist.pair_orders),
        "pair_visits": np.stack(hist.pair_visits),
        "cust_orders": np.stack(hist.cust_orders),
        "cust_disc_orders": np.stack(hist.cust_disc_orders),
        "cust_sessions": np.stack(hist.cust_sessions),
        "weeks": np.asarray(hist.weeks, dtype=np.int64),
        "basket_lengths": lengths,
        "baskets": flat,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".npz.tmp")
    os.close(fd)
    with open(tmp, "wb") as fh:
        np.savez_compressed(fh, **arrays)
    os.replace(tmp, path)  # atomic: parallel exporters never read a half-written file


def _load_serving(path: Path) -> tuple[History, list]:
    with np.load(path) as z:
        hist = History(
            [a for a in z["pair_orders"]],
            [a for a in z["pair_visits"]],
            [a for a in z["cust_orders"]],
            [a for a in z["cust_disc_orders"]],
            [a for a in z["cust_sessions"]],
            [int(w) for w in z["weeks"]],
        )
        ends = np.cumsum(z["basket_lengths"])
        flat = z["baskets"]
        starts = np.r_[0, ends[:-1]]
        baskets = [flat[s:e].copy() for s, e in zip(starts, ends, strict=True)]
    return hist, baskets


def serving_data(market: Market, cache_dir: Path) -> tuple[History, list, str]:
    """The demo's history and each restaurant's usual baskets, from cache when possible."""
    path = Path(cache_dir) / f"serving_{serving_key(market.cfg)}.npz"
    if path.exists():
        try:
            hist, baskets = _load_serving(path)
            return hist, baskets, time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(path.stat().st_mtime))
        except (OSError, ValueError, KeyError):
            pass  # unreadable cache: rebuild below
    hist, light = build_history(market, light=True)
    baskets = restaurant_baskets(light, market.n_rest)
    with suppress(OSError):  # read-only checkout: run without a cache
        _save_serving(path, hist, baskets)
    return hist, baskets, time.strftime("%Y-%m-%dT%H:%M:%S%z")


# ---------------------------------------------------------------- state
class State:
    def __init__(self, settings: Settings):
        self.settings = settings
        art = load_bundle(settings.model_path)
        self.model_meta = {
            k: art.get(k) for k in ("version", "trained_at", "library_versions", "features", "data_sha256", "metrics")
        }
        cfg = Config(**{k: tuple(v) if isinstance(v, list) else v for k, v in art["config"].items()})
        self.terms = Terms(**art["terms"]) if art.get("terms") else Terms()
        self.R = pd.read_csv(settings.data_dir / "restaurants.csv")
        self.market = Market(self.R, cfg, self.terms)
        self.hist, self.baskets, self.data_built_at = serving_data(self.market, settings.cache_dir)
        self.features = HistoryFeatures(self.market, self.hist)
        self.engine = Engine(
            art["model"],
            self.terms,
            art["sigma_rel"],
            art["sigma_orders"],
            holdout=settings.holdout_share,
            topup_value=art["topup_value"],
        )
        self.engine.model_version = str(art.get("version") or "unversioned")
        visits = recent_visits(self.market, self.hist)
        self.visits = dict(tuple(visits.groupby("rest")))
        ids = {int(x) for x in self.R["restaurant_id"]}
        self.restaurant_ids = ids
        self.demo_restaurant = (
            settings.demo_restaurant if settings.demo_restaurant in ids else int(art.get("demo_restaurant", min(ids)))
        )
        # competitors keep today's offers; the restaurant being demonstrated starts without one
        self.background = status_quo_policy(self.market, np.random.default_rng(4242), name="market")
        self.background.discount[self.demo_restaurant] = 0.0
        self.cards = {rid: self._card(rid) for rid in sorted(ids)}  # computed once (audit TL-013)
        self._week_inputs: dict[int, tuple] = {}
        self._week_lock = threading.Lock()
        self.sessions: dict[str, Session] = {}
        self.lock = threading.Lock()
        self._ids = itertools.count(1)
        self._last_evict = time.time()
        self.store = Store(settings.db_path)

    # ---------------- restaurants ----------------
    def _card(self, rid: int) -> dict:
        r = self.R.loc[rid]
        x = self.visits.get(rid)
        local = int(self.market.R.loc[rid, "local"])
        in_loc = self.market.c_loc == self.market.R.loc[rid, "loc"]
        o = self.features.p4[:, local][in_loc]
        regular_orders = o[o >= 3].sum()
        aov = float(self.market.aov[rid])
        return {
            "restaurant_id": rid,
            "name": display_name(r),
            "locality": r["locality"],
            "cuisines": r["cuisines"],
            "rating": float(r["rating"]),
            "aov": aov,
            "orders_per_week": round(float(o.sum()) / 4, 1),
            "regular_customers": int((o >= 3).sum()),
            "regulars_share_of_orders": round(float(regular_orders / max(o.sum(), 1)), 3),
            "menu_visits_per_week": round(len(x) / 2) if x is not None else 0,
            "design_options": design_options(aov),
        }

    def x_for(self, rid: int) -> pd.DataFrame:
        """The restaurant's recent menu visits (the quote's input), features only."""
        return self.visits[rid].drop(columns=["rest", "cust", "week"])

    def locality_frame(self, rid: int) -> pd.DataFrame:
        """One row per (customer, slot) for every customer who can open this restaurant's menu."""
        m = self.market
        local = int(m.R.loc[rid, "local"])
        cust = np.flatnonzero(m.c_loc == m.R.loc[rid, "loc"])
        c = np.tile(cust, 3)
        slot = np.repeat(np.arange(3), len(cust))
        f = self.features.for_exposures(c, np.full(len(c), local), np.full(len(c), rid))
        f.update(slot=slot, reward=np.zeros(len(c)))
        df = pd.DataFrame(f)
        df.insert(0, "cust", c)
        return df

    def new_visitor_row(self, rid: int, slot: int = 2) -> pd.DataFrame:
        """Features of someone with no history at all: decides the table's default."""
        m = self.market
        return pd.DataFrame(
            {
                "c_orders_pw": [0.0],
                "c_disc_share": [0.0],
                "c_weeks_since": [8.0],
                "c_sessions_pw": [0.0],
                "c_no_order_8w": [1.0],
                "c_new_account": [1.0],
                "cr_orders_4w": [0.0],
                "cr_orders_all": [0.0],
                "cr_visits_4w": [0.0],
                "cr_weeks_since": [8.0],
                "r_rating": [m.rating[rid]],
                "r_aov": [m.aov[rid]],
                "r_logvotes": [float(np.log1p(float(m.R.loc[rid, "votes"])))],
                "slot": [slot],
                "reward": [0.0],
            }
        )

    def customer_row(self, cid: int, rid: int, slot: int) -> pd.DataFrame:
        return self.features.for_pair(cid, int(self.market.R.loc[rid, "local"]), rid, slot)

    def in_locality(self, cid: int, rid: int) -> bool:
        return bool(self.market.c_loc[cid] == self.market.R.loc[rid, "loc"])

    def week_inputs(self, w: int) -> tuple[dict, dict]:
        with self._week_lock:
            if w not in self._week_inputs:
                occ = self.market.occasions(w)
                k = occ["rest"].shape[1]
                feats = self.features.for_exposures(
                    np.repeat(occ["cust"], k), occ["local"].ravel(), occ["rest"].ravel()
                )
                self._week_inputs[w] = (occ, feats)
            return self._week_inputs[w]

    # ---------------- sessions and offers ----------------
    def session(self, sid: str) -> Session:
        now = time.time()
        with self.lock:
            if now - self._last_evict > 60:
                idle = self.settings.session_idle_seconds
                for k in [k for k, s in self.sessions.items() if now - s.last_seen > idle]:
                    del self.sessions[k]
                self._last_evict = now
            s = self.sessions.get(sid)
            if s is None:
                s = self.sessions[sid] = Session(sid)
            s.last_seen = now
            return s

    def next_offer_id(self) -> int:
        with self.lock:
            return next(self._ids)

    def all_offers(self) -> list[Offer]:
        with self.lock:
            return [o for s in self.sessions.values() for o in s.offers.values()]
