"""Write data/sample/: exposure and order logs in Zomato's event shapes, from the simulated market.

    python scripts/make_sample_events.py

Three offers run for four simulated weeks through the real service (approval, decision table,
serving hash, weekly logs). Their logs are written in the shapes of docs/events/offer.exposure and
order.placed (flat CSV, one row per event's data), with one full CloudEvents example of every
event type in events_example.jsonl. `scripts/shadow_measure.py` reads the CSV files; Eternal's
engineers can see exactly what they would export to try TrueLift's measurement on their own logs.
Every customer and order here is simulated.
"""

from __future__ import annotations

import hashlib
import json
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "data/sample"
# (restaurant, design overrides): a flat targeted offer, a blanket one, a percentage offer
OFFERS = (
    (233, {"audience": "targeted"}),
    (17, {"audience": "all"}),
    (248, {"audience": "new_to_restaurant", "pct": "card"}),
)


def logs_from_store(store, offers: dict[int, int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The service's exposure and order logs for `offers` ({offer id: restaurant id}), as event data."""
    ex, od = [], []
    for oid, rid in offers.items():
        with store.lock:
            e = pd.read_sql_query(
                "SELECT offer_id, week, visit_id, customer_id, slot, assignment, p0, base_profit, model_version "
                "FROM exposures WHERE offer_id=? AND source='simulated_week' AND assignment IN ('show','control') "
                "ORDER BY week, visit_id",
                store.conn,
                params=(oid,),
            )
            o = pd.read_sql_query(
                "SELECT week, visit_id, customer_id, used_offer, basket, discount FROM orders "
                "WHERE offer_id=? ORDER BY week, visit_id",
                store.conn,
                params=(oid,),
            )
        e.insert(1, "restaurant_id", rid)
        e["visit_id"] = [f"{oid}-{w}-{v}" for w, v in zip(e["week"], e["visit_id"], strict=True)]
        e["decision_table_version"] = f"{oid}-v1"
        o["visit_id"] = [f"{oid}-{w}-{v}" for w, v in zip(o["week"], o["visit_id"], strict=True)]
        o.insert(0, "order_id", [f"o{oid}-{i}" for i in range(len(o))])
        o.insert(2, "restaurant_id", rid)
        o["reward"] = 0.0
        o["zomato_funded"] = 0.0
        o["used_offer"] = o["used_offer"].astype(bool)
        ex.append(e)
        od.append(o.drop(columns=["week"]))
    return pd.concat(ex, ignore_index=True), pd.concat(od, ignore_index=True)


def cloud_event(kind: str, source: str, data: dict, when: datetime) -> dict:
    return {
        "specversion": "1.0",
        "id": str(
            uuid.UUID(
                bytes=hashlib.sha256(f"{kind}{json.dumps(data, sort_keys=True, default=str)}".encode()).digest()[:16]
            )
        ),
        "source": source,
        "type": f"truelift.{kind}",
        "time": when.isoformat().replace("+00:00", "Z"),
        "datacontenttype": "application/json",
        "data": data,
    }


def main() -> int:
    from fastapi.testclient import TestClient

    from truelift.api import app, get_state

    c = TestClient(app)
    h = {"X-Session": "sample-events"}
    c.post("/api/v1/reset", json={}, headers=h)
    made: dict[int, int] = {}
    views = {}
    for rid, over in OFFERS:
        card = c.get(f"/api/v1/restaurants/{rid}").json()
        opts = card["design_options"]
        design = {"discount": opts["default_depth"], "min_order": 0, "audience": "all", "offpeak_only": False}
        design |= {"reward": 0, "zomato_share": 0, "pct": 0}
        design |= {k: v for k, v in over.items() if k != "pct"}
        if over.get("pct") == "card":
            p = next(x for x in opts["pct_offers"] if x["cap"] == opts["default_depth"])
            design |= {"discount": p["cap"], "pct": p["pct"]}
        off = c.post("/api/v1/offers", json={"restaurant_id": rid, "design": design}, headers=h).json()
        c.post(f"/api/v1/offers/{off['offer_id']}/approve", json={"otp": off["demo_otp"]}, headers=h)
        for w in range(1, 5):
            view = c.post(f"/api/v1/offers/{off['offer_id']}/run_week", params={"week": w}, headers=h).json()
            if view["status"] != "active":
                break
        made[off["offer_id"]] = rid
        views[off["offer_id"]] = view
    exposures, orders = logs_from_store(get_state().store, made)
    OUT.mkdir(parents=True, exist_ok=True)
    exposures.to_csv(OUT / "exposures.csv", index=False, lineterminator="\n")
    orders.to_csv(OUT / "orders.csv", index=False, lineterminator="\n")

    # one example of each event type, from the first offer
    oid, rid = next(iter(made.items()))
    v = views[oid]
    t0 = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
    e0 = exposures[exposures["offer_id"] == oid].iloc[0]
    o0 = orders[orders["visit_id"].isin(exposures.loc[exposures["offer_id"] == oid, "visit_id"])].iloc[0]
    last = v["weeks"][-1]["measurement"]
    design = v["design"]
    quote = v["quote"]
    examples = [
        cloud_event(
            "offer.quoted",
            "/truelift/quote",
            {
                "draft_id": f"d{oid}",
                "restaurant_id": rid,
                "design": design,
                "profit_change": quote["profit_change"],
                "profit_low": quote["profit_low"],
                "profit_high": quote["profit_high"],
                "extra_orders": quote["extra_orders"],
                "model_version": v["consent"]["model_version"],
            },
            t0 - timedelta(minutes=5),
        ),
        cloud_event(
            "offer.consented",
            "/zomato/offers",
            {
                "offer_id": oid,
                "restaurant_id": rid,
                "design": design,
                "forecast_shown": quote,
                "evidence_shown": None,
                "who_pays": v["who_pays"],
                "valid_from": t0.isoformat().replace("+00:00", "Z"),
                "valid_to": (t0 + timedelta(weeks=4)).isoformat().replace("+00:00", "Z"),
                "consent_reference": v["consent"]["ledger"]["hash"],
            },
            t0,
        ),
        cloud_event(
            "offer.exposure",
            "/truelift/serve",
            {
                "offer_id": int(e0["offer_id"]),
                "restaurant_id": int(e0["restaurant_id"]),
                "customer_id": int(e0["customer_id"]),
                "visit_id": str(e0["visit_id"]),
                "week": int(e0["week"]),
                "slot": int(e0["slot"]),
                "assignment": str(e0["assignment"]),
                "reason": "matches the owner's audience",
                "p0": float(e0["p0"]),
                "base_profit": float(e0["base_profit"]),
                "decision_table_version": str(e0["decision_table_version"]),
                "model_version": str(e0["model_version"]),
            },
            t0 + timedelta(hours=2),
        ),
        cloud_event(
            "order.placed",
            "/zomato/orders",
            {
                "order_id": str(o0["order_id"]),
                "visit_id": str(o0["visit_id"]),
                "customer_id": int(o0["customer_id"]),
                "restaurant_id": int(o0["restaurant_id"]),
                "basket": float(o0["basket"]),
                "discount": float(o0["discount"]),
                "reward": 0.0,
                "zomato_funded": 0.0,
                "used_offer": bool(o0["used_offer"]),
            },
            t0 + timedelta(hours=2, minutes=4),
        ),
        cloud_event(
            "offer.measured",
            "/truelift/measure",
            {
                "offer_id": oid,
                "week": v["weeks"][-1]["week"],
                "extra_orders": last["orders"]["total"],
                "extra_profit": last["profit"]["total"],
                "extra_profit_low": last["profit"]["low"],
                "extra_profit_high": last["profit"]["high"],
                "weight_on_own_data": last["profit"]["weight_on_own_data"],
                "verdict": last["verdict_code"],
                "sample_ratio_ok": last["sample_ratio"]["ok"],
                "model_version": v["consent"]["model_version"],
            },
            t0 + timedelta(weeks=v["weeks"][-1]["week"]),
        ),
        cloud_event(
            "offer.lifecycle",
            "/zomato/offers",
            {"offer_id": oid, "status": v["status"], "reason": "the four-week approval ended", "renewed_as": None},
            t0 + timedelta(weeks=4),
        ),
    ]
    (OUT / "events_example.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False, default=float) + "\n" for e in examples), encoding="utf-8"
    )
    print(f"wrote {len(exposures)} exposures and {len(orders)} orders for {len(made)} offers to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
