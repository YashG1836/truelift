"""The HTTP contract: every request and response the service accepts or returns.

FastAPI turns these models into the OpenAPI document served at /openapi.json and shown at /docs,
so the four hooks Zomato's systems would call have a readable, typed contract with examples
(audit A02 tier 3, standard S-01). Errors use one shape, RFC 9457 problem details (S-02).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Audience = Literal["all", "new_to_restaurant", "lapsed", "targeted"]


class Schema(BaseModel):
    """Base for every model: fields such as `model_version` are ours, not pydantic's."""

    model_config = ConfigDict(protected_namespaces=())


# ---------------------------------------------------------------- requests
class DesignIn(Schema):
    """An offer as the owner sets it up on the create screen."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "discount": 60,
                    "min_order": 0,
                    "audience": "all",
                    "offpeak_only": False,
                    "reward": 0,
                    "zomato_share": 0,
                }
            ]
        },
    )
    discount: float = Field(60, ge=0, le=1000, description="Rupees off the order; 0 means no discount")
    min_order: float = Field(0, ge=0, le=5000, description="Offer applies only to bills of at least this; 0 = none")
    audience: Audience = Field(
        "all",
        description="Who may see it: everyone, new to the restaurant, "
        "stopped ordering (4+ weeks), or chosen by TrueLift",
    )
    offpeak_only: bool = Field(False, description="Valid 3-6 pm only")
    reward: float = Field(
        0, ge=0, le=500, description="Brand Pack reward per order for regulars (3+ orders in 4 weeks)"
    )
    zomato_share: float = Field(
        0, ge=0, le=1, description="Share of the discount Zomato funds for customers new to Zomato"
    )


class QuoteIn(Schema):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "restaurant_id": 233,
                    "design": {
                        "discount": 60,
                        "min_order": 0,
                        "audience": "all",
                        "offpeak_only": False,
                        "reward": 0,
                        "zomato_share": 0,
                    },
                }
            ]
        },
    )
    restaurant_id: int = Field(ge=0, description="Restaurant (0-299 in the simulated market)")
    design: DesignIn = Field(default_factory=lambda: DesignIn.model_validate({}))


class OtpIn(Schema):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"otp": "4821"}]})
    otp: str = Field(min_length=1, max_length=12, description="The code sent to the owner's registered phone")


class DecisionIn(Schema):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"action": "stop"}]})
    action: Literal["keep", "stop"]


# ---------------------------------------------------------------- shared pieces
class Problem(Schema):
    """RFC 9457 problem details: the one error shape for every failure."""

    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "examples": [
                {
                    "type": "/problems/invalid-design",
                    "title": "Invalid offer design",
                    "status": 422,
                    "detail": "A ₹500 discount is more than 60% of this restaurant's average order (₹150).",
                    "instance": "/api/v1/quote",
                    "correlation_id": "6f1c2e9a",
                }
            ]
        },
    )
    type: str
    title: str
    status: int
    detail: str
    instance: str | None = None
    correlation_id: str | None = None
    errors: list[dict[str, Any]] | None = None


class DesignOut(Schema):
    model_config = ConfigDict(extra="allow")
    discount: float
    min_order: float
    audience: Audience
    offpeak_only: bool
    reward: float
    zomato_share: float


class DesignOptions(Schema):
    """The only design choices the page offers (single source, audit TL-002)."""

    depths: list[int]
    default_depth: int
    min_order: int
    reward: int


class Forecast(Schema):
    """Hook 1 output for one version of an offer: one week, with an 80% range."""

    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "examples": [
                {
                    "design": {
                        "discount": 60,
                        "min_order": 0,
                        "audience": "targeted",
                        "offpeak_only": False,
                        "reward": 0,
                        "zomato_share": 0,
                    },
                    "label": "₹60 off only for customers it brings in",
                    "menu_visits": 3300,
                    "eligible_visits": 905,
                    "redemptions": 121.3,
                    "extra_orders": 52.1,
                    "anyway_share": 0.57,
                    "profit_change": 1731,
                    "profit_low": -552,
                    "profit_high": 4014,
                    "prob_profit_positive": 0.82,
                    "discount_spend": 7278,
                    "reward_spend": 0,
                    "discount_per_extra_order": 140,
                    "zomato_commission_change": 1820,
                    "zomato_funded": 0,
                    "offer_use_rate": 1.0,
                    "order_value_with_offer": 431,
                    "usual_order_value": 431,
                }
            ]
        },
    )
    design: DesignOut
    label: str
    menu_visits: int = Field(description="Menu visits a week behind the forecast")
    eligible_visits: int = Field(description="Visits a week that could see the discount")
    redemptions: float = Field(description="Orders a week expected to use the offer")
    extra_orders: float = Field(description="Of those, orders that happen only because of the offer")
    anyway_share: float | None = Field(description="Share of redemptions that would have come anyway")
    profit_change: int = Field(description="Expected change in the restaurant's profit a week, ₹")
    profit_low: int = Field(description="Low end of the 80% range, ₹")
    profit_high: int = Field(description="High end of the 80% range, ₹")
    prob_profit_positive: float = Field(description="Chance the offer makes the restaurant money, from the forecast")
    advantage: int | None = Field(
        None, description="For a suggested version: expected extra profit a week over the owner's version, ₹"
    )
    discount_spend: int
    reward_spend: int
    discount_per_extra_order: int | None
    zomato_commission_change: int
    zomato_funded: int
    offer_use_rate: float
    order_value_with_offer: int
    usual_order_value: int


class QuoteResponse(Schema):
    owner: Forecast = Field(description="The owner's own design")
    better: Forecast | None = Field(
        description="A better version at the same discount size, or no offer when no version is likely to make "
        "money; null when the owner's version is already the best"
    )
    designs_compared: int
    consent_weeks: int
    model_version: str


class RestaurantCard(Schema):
    model_config = ConfigDict(extra="allow")
    restaurant_id: int
    name: str
    locality: str
    cuisines: str
    rating: float
    aov: float = Field(description="Average order value, ₹")
    orders_per_week: float
    regular_customers: int
    regulars_share_of_orders: float
    menu_visits_per_week: int
    design_options: DesignOptions


class RestaurantList(Schema):
    demo_restaurant: int
    restaurants: list[RestaurantCard]


class OfferCreated(Schema):
    offer_id: int
    status: str
    quote: Forecast
    otp_sent_to: str
    demo_otp: str = Field(description="Shown only because this is a demo; a real OTP never leaves the SMS")
    otp_expires_in_seconds: int


class ServeDecision(Schema):
    """Hook 2 output: what one customer sees when they open the menu."""

    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "examples": [
                {
                    "show_offer": True,
                    "control_group": False,
                    "reason": "likely to order because of the offer",
                    "brand_pack_reward": 0.0,
                    "p_order_without": 0.031,
                    "p_order_with": 0.072,
                    "expected_profit_gain": 4.1,
                    "degraded": False,
                    "model_version": "2026-11-15",
                    "offer_id": 3,
                    "latency_ms": 0.4,
                }
            ]
        },
    )
    show_offer: bool
    control_group: bool = False
    reason: str
    brand_pack_reward: float = 0.0
    brand_pack_control_group: bool = Field(
        default=False, description="A regular held out of the Brand Pack reward (its own control group, TL-016)"
    )
    p_order_without: float = 0.0
    p_order_with: float = 0.0
    expected_profit_gain: float = 0.0
    degraded: bool = False
    model_version: str = ""
    offer_id: int | None = None
    latency_ms: float | None = None


class MeasuredQuantity(Schema):
    model_config = ConfigDict(extra="allow")
    per_visit: float
    per_visit_sd: float
    own_per_visit: float
    own_se: float | None
    model_per_visit: float
    weight_on_own_data: float = Field(description="0 = all from the model, 1 = all from this offer's control group")
    prob_positive: float = Field(description="Chance the true effect is above zero")
    total: float
    low: float
    high: float


class Measurement(Schema):
    """Hook 4: what the offer added so far, with an 80% range and a verdict."""

    model_config = ConfigDict(extra="allow")
    shown_visits: int
    control_visits: int
    profit: MeasuredQuantity
    orders: MeasuredQuantity
    report_today: dict[str, float]
    verdict: str
    verdict_code: Literal["keep", "pause", "probably_losing", "wait", "check_failed"]
    sample_ratio: dict[str, Any] = Field(description="Customers held out against the planned share (A04 M2)")
    pause_check: dict[str, Any] = Field(description="Always-valid bound on the offer's own evidence (TL-017)")


class Payout(Schema):
    model_config = ConfigDict(extra="allow")
    orders: int
    gross_sales: int
    discount_paid_by_you: int
    brand_pack_rewards_paid_by_you: int
    discount_paid_by_zomato: int
    commission: int
    commission_rate: float
    gst_on_commission: int
    gst_rate: float
    net_payout: int


class Experiment(Schema):
    """The two groups the week's number comes from (cumulative)."""

    shown_visits: int
    shown_orders: int
    control_visits: int
    control_orders: int


class BrandPackQuantity(Schema):
    per_visit: float
    total: float
    low: float
    high: float


class BrandPackMeasurement(Schema):
    """The Brand Pack reward measured on its own: regulars who got it against regulars held out."""

    regular_visits: int
    control_visits: int
    orders: BrandPackQuantity | None
    profit: BrandPackQuantity | None
    verdict_code: Literal["pays", "costs", "unclear", "too_early"]
    verdict: str


class WeekResult(Schema):
    model_config = ConfigDict(extra="allow")
    week: int
    measurement: Measurement
    brand_pack: BrandPackMeasurement | None = None
    simulator_truth: dict[str, float] = Field(description="Only a simulation knows this: the offer's true effect")
    payout: Payout
    experiment: Experiment
    whatsapp: str


class ConsentRecord(Schema):
    model_config = ConfigDict(extra="allow")
    approved_at: str = Field(description="ISO 8601 with time zone")
    design: DesignOut
    label: str
    forecast_shown: Forecast
    valid_for_weeks: int
    who_pays: str
    model_version: str
    ledger: dict[str, Any] = Field(description="Position and SHA-256 hash in the append-only consent ledger")


class OfferView(Schema):
    model_config = ConfigDict(extra="allow")
    offer_id: int
    restaurant_id: int
    status: Literal["awaiting_otp", "active", "paused", "stopped", "consent_expired", "replaced", "otp_expired"]
    design: DesignOut
    label: str
    quote: Forecast
    consent: ConsentRecord | None
    weeks: list[WeekResult]
    who_pays: str
    replaced_by: int | None = None


class ConsentCheck(Schema):
    offer_id: int
    record: dict[str, Any]
    seq: int
    hash: str
    prev_hash: str
    verified: bool = Field(description="True if every record in the ledger still matches its hash chain")


class CustomerSample(Schema):
    model_config = ConfigDict(extra="allow")
    customer_id: int
    group: str
    orders_here_4w: int
    orders_here_ever: int
    zomato_orders_per_week: float
    share_of_orders_with_discount: float
    weeks_since_last_order_here: int
    visit_slot: int
    decision: ServeDecision


class CustomersResponse(Schema):
    customers: list[CustomerSample]
    design: DesignOut
    label: str
    offer_id: int | None
    note: str


class ServiceConfig(Schema):
    """Constants the page shares with the service (audit TL-033)."""

    consent_weeks: int
    holdout_share: float
    commission_rate: float
    gst_on_commission: float
    food_cost_share: float
    commission_on: str
    model_version: str
    api_version: str


class Health(Schema):
    status: str


class Ready(Schema):
    status: str
    model_version: str | None = None
    trained_at: str | None = None
    data_built_at: str | None = None
    detail: str | None = None
