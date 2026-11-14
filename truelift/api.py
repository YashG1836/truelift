"""TrueLift service: the hooks Zomato's offer flow would call, plus the demo's own routes.

Run:  uv run uvicorn truelift.api:app --port 8000      (or: python tasks.py serve)
Docs: http://localhost:8000/docs                         (the typed contract, with examples)

Hooks (what Zomato's systems would call), all under /api/v1:
  POST /quote                    offer-creation screen: forecast + better version (before the OTP)
  POST /offers                   create an offer awaiting the owner's OTP
  POST /offers/{id}/approve      owner enters the OTP: consent appended to the hash-chained ledger
  GET  /serve                    menu opened: show the discount to this customer or not (table lookup)
  GET  /offers/{id}              weekly measurement, WhatsApp summary, itemised payout
  POST /offers/{id}/decision     keep / stop (renewal after the consent period needs a new OTP)
  GET  /offers/{id}/consent      the consent record and whether the ledger still verifies
Demo only: /restaurants, /customers, /offers/{id}/run_week, /calls, /example, /evidence, /reset.
Operations: /healthz, /readyz, /metrics, /api/v1/config.

Each browser visitor has their own session (header X-Session); without the header a request
belongs to the shared "public" session. Errors are RFC 9457 problem details.
"""

from __future__ import annotations

import json
import logging
import secrets
import threading
import time
from contextlib import asynccontextmanager, suppress
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import make_asgi_app
from starlette.exceptions import HTTPException as StarletteHTTPException

from .economics import Terms, fmt_inr, weekly_example
from .engine import Design
from .model import BundleError
from .observability import (
    MODEL_INFO,
    OFFERS,
    REGISTRY,
    SERVE_DECISIONS,
    SERVE_FALLBACK,
    ObservabilityMiddleware,
    configure_logging,
)
from .schemas import (
    ConsentCheck,
    CustomersResponse,
    DecisionIn,
    Health,
    OfferCreated,
    OfferView,
    OtpIn,
    Problem,
    QuoteIn,
    QuoteResponse,
    Ready,
    RestaurantCard,
    RestaurantList,
    ServeDecision,
    ServiceConfig,
)
from .settings import ROOT, load_settings
from .state import OTP_MAX_ATTEMPTS, OTP_TTL_SECONDS, Offer, Session, State

STATIC = Path(__file__).resolve().parent / "static"
IST = timezone(timedelta(hours=5, minutes=30))
API_VERSION = "v1"


# ---------------------------------------------------------------- errors (RFC 9457)
class ProblemError(Exception):
    def __init__(self, status: int, kind: str, title: str, detail: str, **extra):
        super().__init__(detail)
        self.status, self.kind, self.title, self.detail, self.extra = status, kind, title, detail, extra


def problem_response(request: Request, status: int, kind: str, title: str, detail: str, **extra) -> JSONResponse:
    body = {
        "type": f"/problems/{kind}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        "correlation_id": request.scope.get("state", {}).get("correlation_id"),
    }
    body.update(extra)
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


PROBLEMS = {
    code: {"model": Problem, "description": text}
    for code, text in (
        (400, "Request body is not valid JSON"),
        (403, "Wrong OTP"),
        (404, "Unknown restaurant, customer or offer"),
        (409, "Offer is in the wrong state"),
        (422, "Invalid input or design"),
        (429, "Too many wrong OTPs"),
        (503, "Model not loaded"),
    )
}


# ---------------------------------------------------------------- state
_state: State | None = None
_state_error: str | None = None
_state_lock = threading.Lock()


def get_state() -> State:
    """The service state, built once (thread-safe); 503 with instructions if the model is missing."""
    global _state, _state_error
    if _state is None:
        with _state_lock:
            if _state is None:
                try:
                    _state = State(load_settings())
                    _state_error = None
                    MODEL_INFO.labels(
                        version=_state.engine.model_version, trained_at=str(_state.model_meta.get("trained_at") or "")
                    ).set(1)
                except BundleError as e:
                    _state_error = str(e)
                    raise ProblemError(503, "model-not-loaded", "The model is not loaded", str(e)) from e
    return _state


def reset_state() -> None:
    """Drop the state so the next request rebuilds it (tests switch models this way)."""
    global _state, _state_error
    with _state_lock:
        _state, _state_error = None, None


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(load_settings().log_json)
    # build before the first request, so nobody waits for it; if the model is missing,
    # /readyz reports it and data routes answer 503 with instructions
    with suppress(ProblemError):
        get_state()
    yield


def session_of(
    request: Request,
    x_session: str | None = Header(None, alias="X-Session", max_length=64, pattern=r"^[A-Za-z0-9_-]{1,64}$"),
) -> Session:
    sid = x_session or "public"
    request.state.session = sid
    return get_state().session(sid)


def log_call(sess: Session, hook: str, t0: float, **info) -> float:
    ms = round((time.perf_counter() - t0) * 1000, 2)
    sess.calls.append({"hook": hook, "ms": ms, **info})
    return ms


def refresh_offer_gauge(s: State) -> None:
    counts: dict[str, int] = {}
    for o in s.all_offers():
        counts[o.status] = counts.get(o.status, 0) + 1
    for status in ("awaiting_otp", "active", "paused", "stopped", "consent_expired", "replaced", "otp_expired"):
        OFFERS.labels(status=status).set(counts.get(status, 0))


def clean(o):
    """JSON-safe values: numpy scalars to Python, infinities to None, floats to six significant
    figures (enough to recompute totals from per-visit values, audit TL-038)."""
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (bool, np.bool_)):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (np.floating, float)):
        if not np.isfinite(o):
            return None
        return float(f"{float(o):.6g}")
    return o


# ---------------------------------------------------------------- checks
def check_restaurant(s: State, rid: int) -> int:
    if rid not in s.restaurant_ids:
        raise ProblemError(404, "unknown-restaurant", "Unknown restaurant", f"There is no restaurant {rid}.")
    if rid not in s.visits:
        raise ProblemError(
            404,
            "unknown-restaurant",
            "No recent visits",
            f"Restaurant {rid} has no menu visits in the last two weeks to forecast from.",
        )
    return rid


def check_design(d: Design, aov: float) -> None:
    """Business rules a request schema cannot know (they depend on the restaurant): audit TL-012."""
    problems = []
    if d.discount > 0.6 * aov:
        problems.append(
            f"A {fmt_inr(d.discount)} discount is more than 60% of this restaurant's average order ({fmt_inr(aov)})."
        )
    if d.min_order > 0 and d.min_order < d.discount:
        problems.append("The minimum order must be at least the discount.")
    if d.min_order > 4 * aov:
        problems.append(f"A minimum order of {fmt_inr(d.min_order)} is more than four times the average order.")
    if d.discount > 0 and d.reward > d.discount:
        problems.append("The Brand Pack reward can't be larger than the discount.")
    if d.discount == 0 and d.reward > 0.6 * aov:
        problems.append("The Brand Pack reward is more than 60% of the average order.")
    if problems:
        raise ProblemError(422, "invalid-design", "Invalid offer design", " ".join(problems))


def get_offer(sess: Session, oid: int) -> Offer:
    off = sess.offers.get(oid)
    if off is None:
        raise ProblemError(404, "unknown-offer", "No such offer", f"There is no offer {oid} in this session.")
    return off


def who_pays(d: Design) -> str:
    if d.zomato_share > 0:
        return (
            f"You pay the discount, except for customers new to Zomato, where Zomato pays "
            f"{d.zomato_share:.0%}. Brand Pack rewards are paid by you."
        )
    return "You pay the discount and any Brand Pack rewards. Nothing is deducted without this approval."


STATUS_TEXT = {
    "awaiting_otp": "waiting for the owner's OTP",
    "active": "running",
    "paused": "paused",
    "stopped": "stopped",
    "consent_expired": "past its approval period",
    "replaced": "replaced by a newer offer",
    "otp_expired": "expired before it was approved",
}


def offer_view(off: Offer) -> dict:
    return clean(
        {
            "offer_id": off.id,
            "restaurant_id": off.restaurant_id,
            "status": off.status,
            "design": asdict(off.design),
            "label": off.design.label(),
            "quote": off.quote,
            "consent": off.consent,
            "weeks": off.weeks,
            "who_pays": who_pays(off.design),
            "replaced_by": off.replaced_by,
        }
    )


# ---------------------------------------------------------------- app
app = FastAPI(
    title="TrueLift",
    version="2.0.0",
    lifespan=lifespan,
    description="Forecast, target and measure restaurant-funded offers by the extra orders and profit they "
    "create. **Hooks** are the calls Zomato's offer flow would make; **demo** routes run the "
    "simulated market behind the prototype. Every figure is simulated.",
    openapi_tags=[
        {"name": "hooks", "description": "The calls Zomato's systems would make"},
        {"name": "demo", "description": "Simulation and demo screens only"},
        {"name": "operations", "description": "Health, readiness, configuration, metrics"},
    ],
)
app.add_middleware(ObservabilityMiddleware)
router = APIRouter(prefix=f"/api/{API_VERSION}", responses=PROBLEMS)


@app.exception_handler(ProblemError)
async def _problem(request: Request, exc: ProblemError):
    return problem_response(request, exc.status, exc.kind, exc.title, exc.detail, **exc.extra)


@app.exception_handler(RequestValidationError)
async def _invalid(request: Request, exc: RequestValidationError):
    errors = [
        {
            "field": ".".join(str(p) for p in e.get("loc", ()) if p not in ("body", "query", "header")),
            "message": e.get("msg", ""),
        }
        for e in exc.errors()
    ]
    detail = "; ".join(f"{e['field']}: {e['message']}" if e["field"] else e["message"] for e in errors[:3])
    return problem_response(request, 422, "invalid-input", "Invalid input", detail or "Invalid input.", errors=errors)


@app.exception_handler(StarletteHTTPException)
async def _http(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 400:  # FastAPI could not decode the body
        return problem_response(
            request, 400, "malformed-body", "Malformed request", "The request body could not be read as JSON."
        )
    kind = {404: "not-found", 405: "method-not-allowed"}.get(exc.status_code, "http-error")
    return problem_response(request, exc.status_code, kind, str(exc.detail), str(exc.detail))


@app.exception_handler(Exception)
async def _internal(request: Request, exc: Exception):
    logging.getLogger("truelift.api").exception("unhandled error")
    return problem_response(
        request,
        500,
        "internal",
        "Internal error",
        "Something went wrong on our side. The correlation id identifies it in the logs.",
    )


# ---------------------------------------------------------------- hooks
@router.post(
    "/quote",
    response_model=QuoteResponse,
    tags=["hooks"],
    summary="Hook 1: forecast an offer and a better version, before the owner's OTP",
)
def quote(q: QuoteIn, request: Request, sess: Session = Depends(session_of)):
    t0 = time.perf_counter()
    s = get_state()
    rid = check_restaurant(s, q.restaurant_id)
    request.state.restaurant = rid
    d = Design(**q.design.model_dump())
    aov = float(s.market.aov[rid])
    check_design(d, aov)
    owner, best = s.engine.best_design(s.x_for(rid), d, aov, s.baskets[rid], weeks=2)
    better = best if best["profit_change"] > owner["profit_change"] + 50 else None
    log_call(sess, "quote", t0, restaurant=rid)
    return clean(
        {
            "owner": owner,
            "better": better,
            "designs_compared": best["designs_compared"],
            "consent_weeks": s.settings.consent_weeks,
            "model_version": s.engine.model_version,
        }
    )


@router.post(
    "/offers",
    response_model=OfferCreated,
    status_code=201,
    tags=["hooks"],
    summary="Create an offer awaiting the owner's OTP",
)
def create_offer(q: QuoteIn, request: Request, sess: Session = Depends(session_of)):
    s = get_state()
    rid = check_restaurant(s, q.restaurant_id)
    request.state.restaurant = rid
    d = Design(**q.design.model_dump())
    aov = float(s.market.aov[rid])
    check_design(d, aov)
    if d.discount <= 0:
        raise ProblemError(
            422,
            "invalid-design",
            "Nothing to approve",
            "This design has no discount, so there is nothing for the owner to approve.",
        )
    qt = s.engine.quote(s.x_for(rid), d, aov, s.baskets[rid], weeks=2)
    oid = s.next_offer_id()
    sess.offers[oid] = Offer(oid, sess.id, rid, d, qt, otp=f"{secrets.randbelow(9000) + 1000}")
    request.state.offer = oid
    refresh_offer_gauge(s)
    return {
        "offer_id": oid,
        "status": "awaiting_otp",
        "quote": clean(qt),
        "otp_sent_to": "owner's registered phone",
        "demo_otp": sess.offers[oid].otp,
        "otp_expires_in_seconds": OTP_TTL_SECONDS,
    }


@router.post(
    "/offers/{oid}/approve",
    response_model=OfferView,
    tags=["hooks"],
    summary="The owner's OTP: consent recorded with exactly what they were shown",
)
def approve(
    oid: int,
    body: OtpIn,
    request: Request,
    sess: Session = Depends(session_of),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=100),
):
    s = get_state()
    off = get_offer(sess, oid)
    request.state.offer = oid
    key = f"approve:{oid}:{idempotency_key}" if idempotency_key else None
    if key and key in sess.idempotency:
        return sess.idempotency[key]
    with off.lock:
        if off.status == "awaiting_otp" and time.time() - off.created_at > OTP_TTL_SECONDS:
            off.status = "otp_expired"
        if off.status != "awaiting_otp":
            hint = " Create the offer again to get a new OTP." if off.status == "otp_expired" else ""
            raise ProblemError(
                409, "offer-state", "This offer can't be approved", f"This offer is {STATUS_TEXT[off.status]}.{hint}"
            )
        if off.otp_attempts >= OTP_MAX_ATTEMPTS:
            raise ProblemError(
                429,
                "too-many-attempts",
                "Too many wrong OTPs",
                "Too many wrong codes. Create the offer again to get a new OTP.",
            )
        if body.otp.strip() != off.otp:
            off.otp_attempts += 1
            left = OTP_MAX_ATTEMPTS - off.otp_attempts
            if left <= 0:
                raise ProblemError(
                    429,
                    "too-many-attempts",
                    "Too many wrong OTPs",
                    "Too many wrong codes. Create the offer again to get a new OTP.",
                )
            attempts = f"{left} attempt{'s' if left != 1 else ''} left"
            raise ProblemError(
                403,
                "wrong-otp",
                "Wrong OTP",
                f"Wrong OTP. Check the code and try again ({attempts}).",
                attempts_left=left,
            )
        rid, d = off.restaurant_id, off.design
        aov = float(s.market.aov[rid])
        off.table = s.engine.decision_table(
            s.locality_frame(rid), d, aov, s.baskets[rid], off.id, s.new_visitor_row(rid)
        )
        if off.table.degraded:
            SERVE_FALLBACK.inc()
        for other in sess.offers.values():  # one running offer per restaurant (audit TL-024)
            if other is not off and other.restaurant_id == rid and other.status == "active":
                other.status, other.replaced_by = "replaced", off.id
        off.status = "active"
        approved_at = datetime.now(IST).isoformat(timespec="seconds")
        record = clean(
            {
                "approved_at": approved_at,
                "design": asdict(d),
                "label": d.label(),
                "forecast_shown": off.quote,
                "valid_for_weeks": s.settings.consent_weeks,
                "who_pays": who_pays(d),
                "model_version": s.engine.model_version,
            }
        )
        ledger = s.store.append_consent(sess.id, off.id, record, approved_at)
        off.consent = {**record, "ledger": {**ledger, "verified": True}}
    refresh_offer_gauge(s)
    view = offer_view(off)
    if key:
        sess.idempotency[key] = view
    return view


@router.get(
    "/serve",
    response_model=ServeDecision,
    tags=["hooks"],
    summary="Hook 2: a customer opens the menu; show the discount or not",
)
def serve(
    request: Request,
    restaurant_id: int = Query(ge=0),
    customer_id: int = Query(ge=0),
    slot: int = Query(2, ge=0, le=2, description="0 lunch, 1 3-6 pm, 2 dinner"),
    sess: Session = Depends(session_of),
):
    t0 = time.perf_counter()
    s = get_state()
    rid = check_restaurant(s, restaurant_id)
    request.state.restaurant = rid
    if customer_id >= s.market.n_cust:
        raise ProblemError(404, "unknown-customer", "Unknown customer", f"There is no customer {customer_id}.")
    if not s.in_locality(customer_id, rid):
        raise ProblemError(
            422,
            "customer-not-in-locality",
            "Customer can't see this restaurant",
            "This customer is not in the restaurant's delivery area.",
        )
    active = [o for o in sess.offers.values() if o.restaurant_id == rid and o.status == "active"]
    if not active:
        SERVE_DECISIONS.labels(decision="no_offer").inc()
        request.state.decision = "no_offer"
        return {
            "show_offer": False,
            "reason": "no active offer",
            "latency_ms": log_call(sess, "serve", t0, restaurant=rid, customer=customer_id, show=False),
        }
    off = active[-1]
    local = int(s.market.R.loc[rid, "local"])
    regular = bool(s.features.p4[customer_id, local] >= 3)
    out = s.engine.serve(off.table, customer_id, slot, regular, off.design.reward)
    out["offer_id"] = off.id
    decision = "control" if out["control_group"] else "show" if out["show_offer"] else "not_eligible"
    SERVE_DECISIONS.labels(decision=decision).inc()
    request.state.decision, request.state.fallback = decision, out["degraded"]
    s.store.log_serve(off.id, customer_id, slot, out, s.engine.model_version)
    out["latency_ms"] = log_call(sess, "serve", t0, restaurant=rid, customer=customer_id, show=out["show_offer"])
    return clean(out)


@router.get(
    "/offers/{oid}",
    response_model=OfferView,
    tags=["hooks"],
    summary="Hook 4: the measured effect so far, the WhatsApp summary and the payout",
)
def get_offer_view(oid: int, sess: Session = Depends(session_of)):
    return offer_view(get_offer(sess, oid))


@router.post("/offers/{oid}/decision", response_model=OfferView, tags=["hooks"], summary="Keep or stop a running offer")
def decision(oid: int, body: DecisionIn, sess: Session = Depends(session_of)):
    off = get_offer(sess, oid)
    with off.lock:
        if body.action == "stop":
            if off.status in ("stopped", "replaced", "otp_expired"):
                raise ProblemError(409, "offer-state", "Nothing to stop", f"This offer is {STATUS_TEXT[off.status]}.")
            off.status = "stopped"
        elif off.status != "active":
            raise ProblemError(
                409,
                "offer-state",
                "Can't keep this offer",
                "Renewing a paused or expired offer needs a fresh quote and a new OTP.",
            )
    refresh_offer_gauge(get_state())
    return offer_view(off)


@router.get(
    "/offers/{oid}/consent",
    response_model=ConsentCheck,
    tags=["hooks"],
    summary="The consent record, and whether the hash-chained ledger still verifies",
)
def consent(oid: int, sess: Session = Depends(session_of)):
    s = get_state()
    get_offer(sess, oid)
    rec = s.store.consent(oid)
    if rec is None:
        raise ProblemError(404, "no-consent", "Not approved yet", "This offer has not been approved yet.")
    ok, _ = s.store.verify()
    return {
        "offer_id": oid,
        "record": rec["record"],
        "seq": rec["seq"],
        "hash": rec["hash"],
        "prev_hash": rec["prev_hash"],
        "verified": ok,
    }


# ---------------------------------------------------------------- demo
@router.get("/restaurants", response_model=RestaurantList, tags=["demo"])
def restaurants():
    s = get_state()
    return {"demo_restaurant": s.demo_restaurant, "restaurants": [s.cards[r] for r in sorted(s.cards)]}


@router.get("/restaurants/{rid}", response_model=RestaurantCard, tags=["demo"])
def restaurant(rid: int):
    s = get_state()
    if rid not in s.cards:
        raise ProblemError(404, "unknown-restaurant", "Unknown restaurant", f"There is no restaurant {rid}.")
    return s.cards[rid]


@router.post(
    "/customers",
    response_model=CustomersResponse,
    tags=["demo"],
    summary="A few of this restaurant's recent visitors and what TrueLift does for each",
)
def sample_customers(q: QuoteIn, sess: Session = Depends(session_of)):
    s = get_state()
    rid = check_restaurant(s, q.restaurant_id)
    aov = float(s.market.aov[rid])
    x = s.visits[rid].drop_duplicates("cust")
    groups = [
        ("regular", x[x["cr_orders_4w"] >= 3]),
        ("stopped ordering", x[(x["cr_orders_all"] > 0) & (x["cr_weeks_since"] >= 4)]),
        ("new to you", x[(x["cr_orders_all"] == 0) & (x["c_new_to_zomato"] == 0)]),
        ("new to Zomato", x[x["c_new_to_zomato"] == 1]),
    ]
    active = [o for o in sess.offers.values() if o.restaurant_id == rid and o.status == "active"]
    off = active[-1] if active else None
    if off is not None:
        d = off.design
    else:
        d = Design(**q.design.model_dump())
        check_design(d, aov)
    slot = 1 if d.offpeak_only else 2  # show customers at a time the offer is valid (audit TL-011)
    picked = [(label, row) for label, g in groups for _, row in g.head(2).iterrows()]
    local = int(s.market.R.loc[rid, "local"])
    if off is None and picked:
        xr = pd.concat([s.customer_row(int(r["cust"]), rid, slot) for _, r in picked], ignore_index=True)
        v = s.engine.design_values(xr, d, aov, s.baskets[rid])
        reasons = s.engine._reasons(xr, d, v["eligible"])
    out = []
    for i, (label, row) in enumerate(picked):
        cid = int(row["cust"])
        regular = bool(s.features.p4[cid, local] >= 3)
        if off is not None:
            dec = s.engine.serve(off.table, cid, slot, regular, d.reward)
        else:
            el = bool(v["eligible"][i])
            dec = {
                "show_offer": el,
                "control_group": False,
                "reason": reasons[i],
                "brand_pack_reward": float(d.reward) if regular else 0.0,
                "p_order_without": round(float(v["p0"][i]), 4),
                "p_order_with": round(float(v["p1"][i]), 4),
                "expected_profit_gain": round(float(v["gain"][i]), 2),
                "degraded": False,
                "model_version": s.engine.model_version,
            }
        out.append(
            {
                "customer_id": cid,
                "group": label,
                "orders_here_4w": int(row["cr_orders_4w"]),
                "orders_here_ever": int(row["cr_orders_all"]),
                "zomato_orders_per_week": round(float(row["c_orders_pw"]), 2),
                "share_of_orders_with_discount": round(float(row["c_disc_share"]), 2),
                "weeks_since_last_order_here": int(row["cr_weeks_since"]),
                "visit_slot": slot,
                "decision": dec,
            }
        )
    note = (
        "Offer running: the customers marked control group are exactly the ones the weekly measurement holds out."
        if off is not None
        else f"Before approval: once the offer starts, 1 in {round(1 / s.engine.holdout)} eligible customers is "
        "held out at random (a hash of customer and offer)."
    )
    return clean(
        {
            "customers": out,
            "design": asdict(d),
            "label": d.label(),
            "offer_id": off.id if off is not None else None,
            "note": note,
        }
    )


@router.post(
    "/offers/{oid}/run_week",
    response_model=OfferView,
    tags=["demo"],
    summary="Demo: simulate the offer's next week (idempotent with ?week=N)",
)
def run_week(
    oid: int, request: Request, week: int | None = Query(None, ge=1, le=52), sess: Session = Depends(session_of)
):
    from .demo import simulate_week

    s = get_state()
    off = get_offer(sess, oid)
    request.state.offer = oid
    with off.lock:  # one week at a time per offer (audit TL-037)
        if week is not None and week <= len(off.weeks):
            return offer_view(off)  # already simulated: return it unchanged
        if week is not None and week != len(off.weeks) + 1:
            raise ProblemError(
                409,
                "offer-state",
                "Weeks run in order",
                f"Week {week} can't be simulated before week {len(off.weeks) + 1}.",
            )
        if off.status != "active":
            raise ProblemError(
                409, "offer-state", "This offer is not running", f"This offer is {STATUS_TEXT[off.status]}."
            )
        wk = clean(simulate_week(s, off))
        off.weeks.append(wk)
        if wk["week"] >= 2 and wk["measurement"]["verdict_code"] == "pause":
            off.status = "paused"
        elif wk["week"] >= s.settings.consent_weeks:
            off.status = "consent_expired"
    refresh_offer_gauge(s)
    return offer_view(off)


@router.get("/calls", tags=["demo"], summary="This session's recent hook calls and their latency")
def calls(sess: Session = Depends(session_of)):
    return {"calls": list(sess.calls)[::-1]}


@router.get("/example", tags=["demo"], summary="The Round 1 worked example, recomputed exactly")
def example(commission_on: Literal["post_discount", "pre_discount"] = "post_discount"):
    return weekly_example(Terms(commission_on=commission_on))


@router.get("/evidence", tags=["demo"], summary="The evaluation reports behind the Evidence page")
def evidence():
    p = ROOT / "reports/evaluation.json"
    if not p.exists():
        raise ProblemError(404, "no-report", "No report", "Run `python scripts/run_pipeline.py` first.")
    out = json.loads(p.read_text(encoding="utf-8"))
    real = ROOT / "reports/uplift_validation_criteo.json"  # check on real randomised data
    if real.exists():
        out["real_data_criteo"] = json.loads(real.read_text(encoding="utf-8"))
    return out


@router.post("/reset", tags=["demo"], summary="Clear this session's offers (other visitors are unaffected)")
def reset(sess: Session = Depends(session_of)):
    sess.offers.clear()
    sess.calls.clear()
    sess.idempotency.clear()
    refresh_offer_gauge(get_state())
    return {"ok": True}


@router.get(
    "/config", response_model=ServiceConfig, tags=["operations"], summary="Constants the page shares with the service"
)
def config():
    s = get_state()
    t = s.terms
    return {
        "consent_weeks": s.settings.consent_weeks,
        "holdout_share": s.engine.holdout,
        "commission_rate": t.commission_rate,
        "gst_on_commission": t.gst_on_commission,
        "food_cost_share": t.food_cost_share,
        "commission_on": t.commission_on,
        "model_version": s.engine.model_version,
        "api_version": API_VERSION,
    }


app.include_router(router)


# ---------------------------------------------------------------- operations
@app.get("/healthz", response_model=Health, tags=["operations"], summary="Process is up")
def healthz():
    return {"status": "ok"}


@app.get(
    "/readyz",
    response_model=Ready,
    tags=["operations"],
    summary="Model and data loaded",
    responses={503: {"model": Ready}},
)
def readyz():
    try:
        s = get_state()
    except ProblemError as e:
        return JSONResponse({"status": "not_ready", "detail": e.detail}, status_code=503)
    return {
        "status": "ready",
        "model_version": s.engine.model_version,
        "trained_at": s.model_meta.get("trained_at"),
        "data_built_at": s.data_built_at,
    }


app.mount("/metrics", make_asgi_app(registry=REGISTRY))
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


def openapi_contract() -> dict:
    """The OpenAPI document, describing errors exactly as they are sent: RFC 9457 problem details
    (`application/problem+json`, schema `Problem`), including FastAPI's own 422 for invalid input."""
    if app.openapi_schema:
        return app.openapi_schema
    spec = get_openapi(
        title=app.title, version=app.version, description=app.description, routes=app.routes, tags=app.openapi_tags
    )
    problem = {"application/problem+json": {"schema": {"$ref": "#/components/schemas/Problem"}}}
    for item in spec.get("paths", {}).values():
        for op in item.values():
            for code, resp in op.get("responses", {}).items():
                if code[0] in "45" and "Problem" in json.dumps(resp.get("content", {})) or code == "422":
                    resp["content"] = problem
                    if code == "422":
                        resp["description"] = "Invalid input or design"
    for unused in ("HTTPValidationError", "ValidationError"):
        spec.get("components", {}).get("schemas", {}).pop(unused, None)
    app.openapi_schema = spec
    return spec


app.openapi = openapi_contract
