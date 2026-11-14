"""Pairs of code paths that must agree (audit testing plan, section 3.2)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tests.conftest import DESIGN, approved_offer


def _offer(state, headers, oid):
    return state.session(headers["X-Session"]).offers[oid]


def _exposures(state, oid):
    with state.store.lock:
        return pd.read_sql_query(
            "SELECT week, customer_id, slot, assignment FROM exposures WHERE offer_id=? AND source='simulated_week'",
            state.store.conn,
            params=(oid,),
        )


def test_serve_and_measurement_share_holdout(client, state, session_headers):
    """TL-004: every customer the measured week held out is a customer `serve` holds out, and
    every customer it showed the offer to is one `serve` shows it to."""
    h = session_headers
    oid = approved_offer(client, h, design={**DESIGN, "audience": "all"})["offer_id"]
    client.post(f"/api/v1/offers/{oid}/run_week", headers=h)
    off = _offer(state, h, oid)
    ex = _exposures(state, oid)
    assert len(ex) > 50
    for _, r in ex.iterrows():
        d = state.engine.serve(off.table, int(r["customer_id"]), int(r["slot"]), False)
        assert d["control_group"] == (r["assignment"] == "control")
        assert d["show_offer"] == (r["assignment"] == "show")


def test_targeted_weeks_use_the_offers_decision_table(client, state, session_headers):
    h = session_headers
    oid = approved_offer(client, h)["offer_id"]  # targeted
    client.post(f"/api/v1/offers/{oid}/run_week", headers=h)
    off = _offer(state, h, oid)
    ex = _exposures(state, oid)
    assert all(off.table.lookup(int(c), int(s))[0] for c, s in zip(ex["customer_id"], ex["slot"], strict=True))


def test_holdout_is_stable_across_weeks(client, state, session_headers):
    h = session_headers
    oid = approved_offer(client, h, design={**DESIGN, "audience": "all"})["offer_id"]
    client.post(f"/api/v1/offers/{oid}/run_week", headers=h)
    client.post(f"/api/v1/offers/{oid}/run_week", headers=h)
    ex = _exposures(state, oid)
    per_customer = ex.groupby("customer_id")["assignment"].nunique()
    assert (per_customer == 1).all()  # a held-out customer stays held out for the offer's life


def test_measurement_from_log_equals_measurement_from_rows(client, state, session_headers):
    """TL-028: the week measured from the exposure and order logs equals the week measured
    directly from the simulated rows."""
    from truelift.demo import week_rows

    h = session_headers
    oid = approved_offer(client, h, design={**DESIGN, "audience": "all"})["offer_id"]
    view = client.post(f"/api/v1/offers/{oid}/run_week", headers=h).json()
    off = _offer(state, h, oid)
    _, el = week_rows(state, off, 1)
    aov = float(state.market.aov[off.restaurant_id])
    direct = state.engine.measure(
        el,
        aov,
        float(el["gain"].mean()),
        float((el["p1"] - el["p0"]).mean()),
        el["base_profit"].to_numpy(),
        el["p0"].to_numpy(),
    )
    logged = view["weeks"][0]["measurement"]
    for key in ("profit", "orders"):
        for f in ("total", "low", "high", "weight_on_own_data"):
            assert logged[key][f] == pytest.approx(direct[key][f], rel=1e-5, abs=1e-6)
    assert logged["report_today"]["orders_with_offer"] == direct["report_today"]["orders_with_offer"]


def test_payout_identity_holds_every_week(client, session_headers):
    h = session_headers
    oid = approved_offer(client, h)["offer_id"]
    for _ in range(2):
        client.post(f"/api/v1/offers/{oid}/run_week", headers=h)
    for w in client.get(f"/api/v1/offers/{oid}", headers=h).json()["weeks"]:
        p = w["payout"]
        assert (
            p["gst_on_commission"] == round(p["gst_rate"] * p["commission"])
            or abs(p["gst_on_commission"] - p["gst_rate"] * p["commission"]) <= 1
        )
        assert p["net_payout"] == (
            p["gross_sales"]
            - p["discount_paid_by_you"]
            - p["brand_pack_rewards_paid_by_you"]
            - p["commission"]
            - p["gst_on_commission"]
        )


def test_engine_does_not_import_the_simulator():
    """A02: the code Zomato would run (engine, model, economics, assignment, features) does not
    depend on the simulator."""
    import subprocess
    import sys

    code = (
        "import sys; import truelift.engine, truelift.features, truelift.assignment; "
        "print('truelift.sim' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "False"


def test_quote_input_and_serving_rows_have_the_same_features(state):
    """The quote's visit table and the serving lookup compute a customer's features the same way:
    a visit in week w carries the features of the history before w (no look-ahead, TL-006)."""
    from truelift.features import HistoryFeatures

    rid = 233
    v = state.visits[rid]
    v = v[v["week"] == -1].iloc[:20]
    then = HistoryFeatures(state.market, state.hist.before(-1))
    local = int(state.market.R.loc[rid, "local"])
    for _, r in v.iterrows():
        row = then.for_pair(int(r["cust"]), local, rid, int(r["slot"]))
        for col in ("c_orders_pw", "cr_orders_4w", "cr_orders_all", "cr_weeks_since", "c_no_order_8w"):
            assert row[col].iloc[0] == pytest.approx(float(r[col]))
    assert np.isfinite(v.select_dtypes("number").to_numpy()).all()


def test_renewal_shows_the_measured_evidence_and_keeps_the_control_group(client, state, session_headers):
    """A09 D3: after the approval period the owner renews on what was measured; the consent record
    stores that evidence; the same customers stay held out; the renewed weeks are new weeks."""
    h = session_headers
    first = None
    for design in ({**DESIGN, "audience": "all"}, DESIGN, {**DESIGN, "audience": "new_to_restaurant"}):
        oid = approved_offer(client, h, design=design)["offer_id"]
        assert client.post(f"/api/v1/offers/{oid}/renew", headers=h).status_code == 409  # still running
        for w in range(1, 5):
            view = client.post(f"/api/v1/offers/{oid}/run_week", params={"week": w}, headers=h).json()
            if view["status"] != "active":
                break
        if view["status"] == "paused":  # a losing offer is changed, not renewed
            assert client.post(f"/api/v1/offers/{oid}/renew", headers=h).status_code == 409
            continue
        first = view
        break
    assert first is not None and first["status"] == "consent_expired"
    oid = first["offer_id"]
    r = client.post(f"/api/v1/offers/{oid}/renew", headers=h)
    assert r.status_code == 201, r.text
    new = r.json()
    ev, last = new["evidence"], first["weeks"][-1]["measurement"]
    assert new["renewal_of"] == oid and ev["weeks"] == len(first["weeks"])
    assert ev["extra_profit"] == pytest.approx(last["profit"]["total"], rel=1e-5)
    assert ev["extra_profit_low"] <= ev["extra_profit"] <= ev["extra_profit_high"]
    assert ev["verdict_code"] == last["verdict_code"]
    ok = client.post(f"/api/v1/offers/{new['offer_id']}/approve", json={"otp": new["demo_otp"]}, headers=h).json()
    assert ok["consent"]["renewal_of"] == oid and ok["consent"]["evidence_shown"] == ev
    assert client.get(f"/api/v1/offers/{oid}", headers=h).json()["renewed_by"] == new["offer_id"]
    assert client.post(f"/api/v1/offers/{oid}/renew", headers=h).status_code == 409  # renewed once only
    assert client.get(f"/api/v1/offers/{new['offer_id']}/consent", headers=h).json()["verified"]
    # the same control group, and weeks after the first period (not a replay of them)
    old_off, new_off = _offer(state, h, oid), _offer(state, h, new["offer_id"])
    assert new_off.table.offer_id == old_off.table.offer_id == oid
    wk = client.post(f"/api/v1/offers/{new['offer_id']}/run_week", headers=h).json()["weeks"][-1]
    assert wk["week"] == 1 and wk["experiment"] != first["weeks"][0]["experiment"]
    old_held = set(_exposures(state, oid).query("assignment == 'control'")["customer_id"])
    new_ex = _exposures(state, new["offer_id"])
    both = set(new_ex["customer_id"]) & set(_exposures(state, oid)["customer_id"])
    for c in both:  # a customer seen in both periods is held out in both or in neither
        held_now = (new_ex.loc[new_ex["customer_id"] == c, "assignment"] == "control").any()
        assert held_now == (c in old_held)


def test_demo_week_of_one_restaurant_equals_the_full_market(client, state, session_headers):
    """The demo simulates only the occasions in which the offer's restaurant was opened; its rows
    must be exactly those of a full-market week (same visits, outcomes, truth and visit ids)."""
    from truelift.demo import week_rows

    for design in ({**DESIGN, "audience": "all"}, DESIGN, {**DESIGN, "discount": 60, "pct": 0.3}):
        oid = approved_offer(client, session_headers, design=design)["offer_id"]
        off = _offer(state, session_headers, oid)
        for w in (1, 3):
            fast, fast_el = week_rows(state, off, w)
            full, full_el = week_rows(state, off, w, full_market=True)
            pd.testing.assert_frame_equal(fast, full)
            pd.testing.assert_frame_equal(fast_el, full_el)
