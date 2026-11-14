"""The shadow kit (scripts/shadow_measure.py) and the event shapes (docs/events/): what Zomato's
engineers would run on their own logs gives the service's own estimate, and the sample events
match their schemas (integration blueprint, audit A14)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.make_sample_events import logs_from_store
from scripts.shadow_measure import measure_files
from tests.conftest import DESIGN, approved_offer

ROOT = Path(__file__).resolve().parents[1]


def test_shadow_kit_reproduces_the_services_own_estimate(client, state, session_headers):
    h = session_headers
    rid = 233
    oid = approved_offer(client, h, rid, design={**DESIGN, "audience": "all"})["offer_id"]
    for w in (1, 2):
        view = client.post(f"/api/v1/offers/{oid}/run_week", params={"week": w}, headers=h).json()
    exposures, orders = logs_from_store(state.store, {oid: rid})
    res = measure_files(exposures, orders, state.terms, state.engine.holdout, 4)[0]
    got, want = res["weeks"][-1], view["weeks"][-1]["measurement"]
    assert got["shown_visits"] == want["shown_visits"] and got["control_visits"] == want["control_visits"]
    assert got["regression_adjusted"]
    assert got["profit"]["per_visit"] == pytest.approx(want["profit"]["own_per_visit"], rel=1e-4, abs=1e-6)
    assert got["sample_ratio"]["ok"] == want["sample_ratio"]["ok"]
    assert len(res["weeks"]) == 2  # one cumulative result per week


def test_sample_events_match_their_schemas():
    jsonschema_rs = pytest.importorskip("jsonschema_rs")
    lines = (ROOT / "data/sample/events_example.jsonl").read_text(encoding="utf-8").splitlines()
    kinds = set()
    for line in lines:
        event = json.loads(line)
        kind = event["type"].removeprefix("truelift.")
        schema = json.loads((ROOT / f"docs/events/{kind}.schema.json").read_text(encoding="utf-8"))
        jsonschema_rs.validate(schema, event)
        kinds.add(kind)
    assert kinds == {p.name.removesuffix(".schema.json") for p in (ROOT / "docs/events").glob("*.schema.json")}


def test_sample_logs_have_the_columns_the_kit_reads():
    import pandas as pd

    ex = pd.read_csv(ROOT / "data/sample/exposures.csv")
    od = pd.read_csv(ROOT / "data/sample/orders.csv")
    assert {"offer_id", "restaurant_id", "customer_id", "visit_id", "week", "assignment", "base_profit"} <= set(ex)
    assert {"order_id", "visit_id", "basket", "discount", "used_offer"} <= set(od)
    assert set(ex["assignment"]) == {"show", "control"} and od["visit_id"].isin(ex["visit_id"]).all()
