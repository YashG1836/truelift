"""The service as a client sees it: the happy path, every way it should refuse, sessions,
concurrency, the consent ledger, and the operational endpoints."""

from __future__ import annotations

import os
import shutil
import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.conftest import DESIGN, approved_offer
from truelift.model import BundleError, load_bundle, save_bundle


def test_api_end_to_end(client, session_headers):
    h = session_headers
    rid = client.get("/api/v1/restaurants").json()["demo_restaurant"]
    q = client.post("/api/v1/quote", json={"restaurant_id": rid, "design": DESIGN}, headers=h).json()
    assert q["owner"]["profit_low"] <= q["owner"]["profit_change"] <= q["owner"]["profit_high"]
    assert q["model_version"] == "test-small"
    off = client.post("/api/v1/offers", json={"restaurant_id": rid, "design": DESIGN}, headers=h).json()
    oid = off["offer_id"]
    assert client.post(f"/api/v1/offers/{oid}/approve", json={"otp": "0000"}, headers=h).status_code == 403
    ok = client.post(f"/api/v1/offers/{oid}/approve", json={"otp": off["demo_otp"]}, headers=h).json()
    assert ok["status"] == "active" and ok["consent"]["forecast_shown"]["label"]
    assert ok["consent"]["approved_at"].endswith("+05:30")  # the moment of approval, with its time zone
    cust = client.post("/api/v1/customers", json={"restaurant_id": rid, "design": DESIGN}, headers=h).json()
    assert cust["offer_id"] == oid and len(cust["customers"]) >= 4
    s = client.get(
        "/api/v1/serve", params={"restaurant_id": rid, "customer_id": cust["customers"][0]["customer_id"]}, headers=h
    ).json()
    assert "show_offer" in s and s["latency_ms"] < 50 and s["offer_id"] == oid
    wk = client.post(f"/api/v1/offers/{oid}/run_week", headers=h).json()["weeks"][-1]
    p = wk["payout"]
    assert p["net_payout"] == (
        p["gross_sales"]
        - p["discount_paid_by_you"]
        - p["brand_pack_rewards_paid_by_you"]
        - p["commission"]
        - p["gst_on_commission"]
    )
    assert p["commission_rate"] == 0.25 and p["gst_rate"] == 0.18
    assert "TrueLift weekly summary" in wk["whatsapp"]
    e = wk["experiment"]
    assert e["shown_visits"] == wk["measurement"]["shown_visits"]
    assert e["control_visits"] == wk["measurement"]["control_visits"]


@pytest.mark.parametrize(
    "path, body, params, status, kind",
    [
        ("/api/v1/quote", {"restaurant_id": 0, "design": {**DESIGN, "discount": 500}}, None, 422, "invalid-design"),
        ("/api/v1/quote", {"restaurant_id": 233, "design": {**DESIGN, "discount": -5}}, None, 422, "invalid-input"),
        ("/api/v1/quote", {"restaurant_id": 233, "design": {**DESIGN, "audience": "rich"}}, None, 422, "invalid-input"),
        ("/api/v1/quote", {"restaurant_id": 233, "design": {**DESIGN, "min_order": 30}}, None, 422, "invalid-design"),
        ("/api/v1/quote", {"restaurant_id": 233, "design": {**DESIGN, "reward": 80}}, None, 422, "invalid-design"),
        ("/api/v1/quote", {"restaurant_id": 233, "design": {**DESIGN, "colour": "red"}}, None, 422, "invalid-input"),
        ("/api/v1/quote", {"restaurant_id": 99999, "design": DESIGN}, None, 404, "unknown-restaurant"),
        ("/api/v1/offers", {"restaurant_id": 233, "design": {**DESIGN, "discount": 0}}, None, 422, "invalid-design"),
        ("/api/v1/serve", None, {"restaurant_id": 233, "customer_id": 10_000_000}, 404, "unknown-customer"),
        ("/api/v1/serve", None, {"restaurant_id": 233, "customer_id": -1}, 422, "invalid-input"),
        ("/api/v1/serve", None, {"restaurant_id": 233, "customer_id": 1, "slot": 99}, 422, "invalid-input"),
        ("/api/v1/offers/424242", None, None, 404, "unknown-offer"),
    ],
)
def test_invalid_inputs_return_problem_details(client, session_headers, path, body, params, status, kind):
    r = (
        client.post(path, json=body, headers=session_headers)
        if body is not None
        else client.get(path, params=params, headers=session_headers)
    )
    assert r.status_code == status, r.text
    assert r.headers["content-type"].startswith("application/problem+json")
    p = r.json()
    assert p["type"] == f"/problems/{kind}" and p["status"] == status
    assert isinstance(p["detail"], str) and p["detail"]
    assert p["correlation_id"] == r.headers["x-correlation-id"]


def test_customer_outside_the_restaurants_area_is_refused(client, state, session_headers):
    rid = 233
    other = int(next(c for c in range(state.market.n_cust) if not state.in_locality(c, rid)))
    r = client.get("/api/v1/serve", params={"restaurant_id": rid, "customer_id": other}, headers=session_headers)
    assert r.status_code == 422 and r.json()["type"] == "/problems/customer-not-in-locality"


def test_bad_session_header_is_refused(client):
    r = client.post("/api/v1/reset", json={}, headers={"X-Session": "no spaces allowed!"})
    assert r.status_code == 422


def test_sessions_are_isolated(client):
    a, b = {"X-Session": "alice" + uuid.uuid4().hex[:6]}, {"X-Session": "bob" + uuid.uuid4().hex[:6]}
    off = approved_offer(client, a)
    assert client.post("/api/v1/reset", json={}, headers=b).json()["ok"]
    assert client.get(f"/api/v1/offers/{off['offer_id']}", headers=a).json()["status"] == "active"
    assert client.get(f"/api/v1/offers/{off['offer_id']}", headers=b).status_code == 404


def test_offer_ids_unique_after_reset(client, session_headers):
    first = approved_offer(client, session_headers)["offer_id"]
    client.post("/api/v1/reset", json={}, headers=session_headers)
    second = approved_offer(client, session_headers)["offer_id"]
    assert second != first


def test_one_active_offer_per_restaurant(client, session_headers):
    h = session_headers
    first = approved_offer(client, h)
    second = approved_offer(client, h, design={**DESIGN, "audience": "all"})
    old = client.get(f"/api/v1/offers/{first['offer_id']}", headers=h).json()
    assert old["status"] == "replaced" and old["replaced_by"] == second["offer_id"]
    assert client.post(f"/api/v1/offers/{first['offer_id']}/run_week", headers=h).status_code == 409


def test_status_transitions(client, session_headers):
    h = session_headers
    off = client.post("/api/v1/offers", json={"restaurant_id": 233, "design": DESIGN}, headers=h).json()
    oid = off["offer_id"]
    assert client.post(f"/api/v1/offers/{oid}/run_week", headers=h).status_code == 409  # not approved yet
    client.post(f"/api/v1/offers/{oid}/approve", json={"otp": off["demo_otp"]}, headers=h)
    assert client.post(f"/api/v1/offers/{oid}/approve", json={"otp": off["demo_otp"]}, headers=h).status_code == 409
    decide = f"/api/v1/offers/{oid}/decision"
    assert client.post(decide, json={"action": "keep"}, headers=h).json()["status"] == "active"
    assert client.post(decide, json={"action": "stop"}, headers=h).json()["status"] == "stopped"
    assert client.post(f"/api/v1/offers/{oid}/decision", json={"action": "keep"}, headers=h).status_code == 409
    assert client.post(f"/api/v1/offers/{oid}/decision", json={"action": "stop"}, headers=h).status_code == 409


def test_otp_attempt_limit(client, session_headers):
    h = session_headers
    off = client.post("/api/v1/offers", json={"restaurant_id": 233, "design": DESIGN}, headers=h).json()
    url = f"/api/v1/offers/{off['offer_id']}/approve"
    codes = [client.post(url, json={"otp": "0000"}, headers=h).status_code for _ in range(5)]
    assert codes == [403, 403, 403, 403, 429]
    assert client.post(url, json={"otp": off["demo_otp"]}, headers=h).status_code == 429  # locked


def test_otp_expiry(client, state, session_headers):
    h = session_headers
    off = client.post("/api/v1/offers", json={"restaurant_id": 233, "design": DESIGN}, headers=h).json()
    state.session(h["X-Session"]).offers[off["offer_id"]].created_at -= 3600
    r = client.post(f"/api/v1/offers/{off['offer_id']}/approve", json={"otp": off["demo_otp"]}, headers=h)
    assert r.status_code == 409 and "new OTP" in r.json()["detail"]


def test_idempotency_key_on_approve(client, session_headers):
    h = session_headers
    off = client.post("/api/v1/offers", json={"restaurant_id": 233, "design": DESIGN}, headers=h).json()
    url = f"/api/v1/offers/{off['offer_id']}/approve"
    hk = {**h, "Idempotency-Key": "k1"}
    a = client.post(url, json={"otp": off["demo_otp"]}, headers=hk)
    b = client.post(url, json={"otp": off["demo_otp"]}, headers=hk)
    assert a.status_code == b.status_code == 200 and a.json() == b.json()


def test_run_week_is_idempotent_with_week_number(client, session_headers):
    h = session_headers
    oid = approved_offer(client, h)["offer_id"]
    one = client.post(f"/api/v1/offers/{oid}/run_week", params={"week": 1}, headers=h).json()
    again = client.post(f"/api/v1/offers/{oid}/run_week", params={"week": 1}, headers=h).json()
    assert len(one["weeks"]) == len(again["weeks"]) == 1
    assert client.post(f"/api/v1/offers/{oid}/run_week", params={"week": 3}, headers=h).status_code == 409


def test_run_week_concurrent_calls_append_once(client, service_env):
    from truelift.api import app

    h = {"X-Session": "race" + uuid.uuid4().hex[:6]}
    oid = approved_offer(client, h)["offer_id"]
    results = []

    def go():
        with TestClient(app) as c:
            results.append(c.post(f"/api/v1/offers/{oid}/run_week", params={"week": 1}, headers=h).status_code)

    threads = [threading.Thread(target=go) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results == [200] * 4
    assert len(client.get(f"/api/v1/offers/{oid}", headers=h).json()["weeks"]) == 1


def test_concurrent_quotes_match_sequential(client, service_env):
    """TL-001: eight threads mixing quotes and customer panels for six restaurants get exactly the
    answers a single caller gets."""
    from truelift.api import app

    rids = [233, 57, 142, 273, 17, 84]
    h = {"X-Session": "conc" + uuid.uuid4().hex[:6]}

    def call(c, i):
        rid = rids[i % len(rids)]
        body = {"restaurant_id": rid, "design": DESIGN}
        if i % 2:
            return ("customers", rid, c.post("/api/v1/customers", json=body, headers=h).json())
        return ("quote", rid, c.post("/api/v1/quote", json=body, headers=h).json())

    expected = {(kind, rid): out for kind, rid, out in (call(client, i) for i in range(12))}
    errors, mismatches = [], []

    def worker(k):
        with TestClient(app) as c:
            for j in range(20):
                try:
                    kind, rid, out = call(c, k + j)
                except Exception as e:  # noqa: BLE001
                    errors.append(repr(e))
                    continue
                if out != expected[(kind, rid)]:
                    mismatches.append((kind, rid))

    threads = [threading.Thread(target=worker, args=(k,)) for k in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == [] and mismatches == []


def test_offpeak_sample_customers_use_offpeak_slot(client, session_headers):
    """TL-011: for a 3-6 pm offer the sample customers are shown at 3-6 pm, so some can see it."""
    d = {**DESIGN, "audience": "all", "offpeak_only": True}
    out = client.post("/api/v1/customers", json={"restaurant_id": 233, "design": d}, headers=session_headers).json()
    assert all(c["visit_slot"] == 1 for c in out["customers"])
    assert any(c["decision"]["show_offer"] for c in out["customers"])


def test_customers_have_no_control_tag_before_approval(client, session_headers):
    d = {**DESIGN, "audience": "all"}
    out = client.post("/api/v1/customers", json={"restaurant_id": 233, "design": d}, headers=session_headers).json()
    assert out["offer_id"] is None and not any(c["decision"]["control_group"] for c in out["customers"])
    assert "held out" in out["note"]


def test_restaurants_endpoint_is_fast_and_carries_design_options(client):
    client.get("/api/v1/restaurants")
    t0 = time.perf_counter()
    r = client.get("/api/v1/restaurants")
    assert (time.perf_counter() - t0) < 0.25  # was over a second (TL-013)
    card = r.json()["restaurants"][0]
    assert set(card["design_options"]) == {"depths", "default_depth", "min_order", "reward"}


def test_config_shares_the_constants_the_page_needs(client):
    c = client.get("/api/v1/config").json()
    assert c["consent_weeks"] == 4 and c["holdout_share"] == 0.10
    assert c["commission_rate"] == 0.25 and c["gst_on_commission"] == 0.18 and c["api_version"] == "v1"


def test_example_supports_both_commission_bases(client):
    post = client.get("/api/v1/example").json()["per_order_discounted"]["commission"]
    pre = client.get("/api/v1/example", params={"commission_on": "pre_discount"}).json()
    pre = pre["per_order_discounted"]["commission"]
    assert post == 85.0 and pre == 100.0


def test_consent_record_verifies_and_detects_tampering(client, state, session_headers):
    off = approved_offer(client, session_headers)
    c = client.get(f"/api/v1/offers/{off['offer_id']}/consent", headers=session_headers).json()
    assert c["verified"] and c["record"]["label"] == off["label"] and len(c["hash"]) == 64
    with state.store.lock, state.store.conn:  # change one byte of the stored record
        state.store.conn.execute("UPDATE consents SET payload = payload || ' ' WHERE seq = ?", (c["seq"],))
    try:
        assert state.store.verify() == (False, c["seq"])
        r = client.get(f"/api/v1/offers/{off['offer_id']}/consent", headers=session_headers).json()
        assert r["verified"] is False
    finally:
        with state.store.lock, state.store.conn:
            state.store.conn.execute(
                "UPDATE consents SET payload = substr(payload, 1, length(payload) - 1) WHERE seq = ?", (c["seq"],)
            )
    assert state.store.verify() == (True, None)


def test_health_readiness_and_metrics(client, session_headers):
    assert client.get("/healthz").json() == {"status": "ok"}
    r = client.get("/readyz").json()
    assert r["status"] == "ready" and r["model_version"] == "test-small"
    approved_offer(client, session_headers)
    client.get("/api/v1/serve", params={"restaurant_id": 233, "customer_id": 1}, headers=session_headers)
    text = client.get("/metrics").text
    for name in (
        "truelift_request_seconds",
        "truelift_serve_decisions_total",
        "truelift_serve_fallback_total",
        "truelift_holdout_share",
        "truelift_offers",
        "truelift_model_info",
        "truelift_forecast_minus_measured_ratio",
    ):
        assert name in text, name
    assert "truelift_serve_fallback_total 0.0" in text


def test_security_headers(client):
    r = client.get("/")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert "content-security-policy" not in client.get("/docs").headers  # Swagger UI loads its own assets


def test_openapi_names_every_hook_response(client):
    spec = client.get("/openapi.json").json()
    hooks = (
        ("/api/v1/quote", "post", "QuoteResponse"),
        ("/api/v1/serve", "get", "ServeDecision"),
        ("/api/v1/offers/{oid}", "get", "OfferView"),
        ("/api/v1/offers", "post", "OfferCreated"),
    )
    for path, method, model in hooks:
        ok = spec["paths"][path][method]["responses"]
        ref = next(iter(ok.get("200", ok.get("201"))["content"]["application/json"]["schema"].values()))
        assert ref.endswith(model)
    assert "Problem" in spec["components"]["schemas"]


def test_missing_model_returns_503_with_instructions(client, monkeypatch, tmp_path):
    from truelift import api

    monkeypatch.setenv("TRUELIFT_MODEL", str(tmp_path / "nothing.pkl"))
    api.reset_state()
    try:
        r = client.get("/api/v1/restaurants")
        assert r.status_code == 503 and r.json()["type"] == "/problems/model-not-loaded"
        assert "run_pipeline.py" in r.json()["detail"]
        assert client.get("/readyz").status_code == 503
        assert client.get("/healthz").status_code == 200
    finally:
        monkeypatch.undo()
        api.reset_state()


def test_model_hash_mismatch_is_refused(service_env, tmp_path):
    src = service_env / "model.pkl"
    dst = tmp_path / "model.pkl"
    shutil.copy(src, dst)
    shutil.copy(src.with_name("model.pkl.sha256"), dst.with_name("model.pkl.sha256"))
    load_bundle(dst)  # intact copy loads
    with open(dst, "ab") as fh:
        fh.write(b"tampered")
    with pytest.raises(BundleError, match="checksum"):
        load_bundle(dst)
    os.remove(dst.with_name("model.pkl.sha256"))
    with pytest.raises(BundleError, match="cannot be verified"):
        load_bundle(dst)


def test_model_bundle_version_check(tmp_path):
    save_bundle({"library_versions": {"scikit-learn": "0.0.1"}, "model": None}, tmp_path / "m.pkl")
    with pytest.raises(BundleError, match="scikit-learn 0.0.1"):
        load_bundle(tmp_path / "m.pkl")


def test_clean_preserves_small_values():
    """TL-038: six significant figures, so per-visit values still add up to the totals."""
    import numpy as np

    from truelift.api import clean

    out = clean({"a": np.float64(0.000123456789), "b": [np.int64(3), np.bool_(True)], "c": float("inf")})
    assert out == {"a": 0.000123457, "b": [3, True], "c": None}
    assert type(out["b"][0]) is int and type(out["b"][1]) is bool
    assert clean(123456789.0) == 123457000.0


def test_payout_uses_terms():
    """TL-033: the payout's rates come from Terms, and the lines add up to the net payout."""
    import pandas as pd

    from truelift.demo import payout_for
    from truelift.economics import Terms

    orders = pd.DataFrame(
        {
            "basket": [400.0, 500.0],
            "restaurant_funded": [60.0, 0.0],
            "zomato_funded": [0.0, 30.0],
            "reward": [0.0, 0.0],
            "commission": [85.0, 117.5],
        }
    )
    terms = Terms(commission_rate=0.20, gst_on_commission=0.18)
    p = payout_for(orders, terms)
    assert p["commission_rate"] == 0.20 and p["gst_rate"] == 0.18
    assert p["gst_on_commission"] == round(0.18 * 202.5)
    assert p["net_payout"] == 900 - 60 - 0 - 202 - 36


def test_card_values_match_the_raw_history(client, state):
    """TL-013: cached cards say what the history says (recomputed here from the weekly arrays)."""
    import numpy as np

    card = client.get("/api/v1/restaurants/233").json()
    m = state.market
    local = int(m.R.loc[233, "local"])
    in_loc = m.c_loc == m.R.loc[233, "loc"]
    last4 = np.sum(np.stack(state.hist.pair_orders[-4:]), axis=0)[:, local][in_loc]
    assert card["orders_per_week"] == round(float(last4.sum()) / 4, 1)
    assert card["regular_customers"] == int((last4 >= 3).sum())


def test_fallback_counter_stays_zero_after_a_normal_flow(client, session_headers):
    """A16 O3: a healthy model never takes the fallback path."""
    off = approved_offer(client, session_headers)
    client.post(f"/api/v1/offers/{off['offer_id']}/run_week", headers=session_headers)
    for cid in range(5):
        client.get("/api/v1/serve", params={"restaurant_id": 233, "customer_id": cid}, headers=session_headers)
    assert "truelift_serve_fallback_total 0.0" in client.get("/metrics").text


def test_openapi_documents_errors_as_problem_details(client):
    """Errors are documented exactly as sent: application/problem+json with the Problem schema."""
    spec = client.get("/openapi.json").json()
    for path, method in (("/api/v1/quote", "post"), ("/api/v1/serve", "get"), ("/api/v1/offers/{oid}/approve", "post")):
        responses = spec["paths"][path][method]["responses"]
        for code in ("400", "404", "422"):
            content = responses[code]["content"]
            assert list(content) == ["application/problem+json"], (path, code)
            assert content["application/problem+json"]["schema"]["$ref"].endswith("/Problem")
    assert "HTTPValidationError" not in spec["components"]["schemas"]


def test_malformed_body_is_a_problem_not_a_crash(client, session_headers):
    r = client.post(
        "/api/v1/quote", content=b"\xff\xfe not json", headers={**session_headers, "Content-Type": "application/json"}
    )
    assert r.status_code in (400, 422)
    assert r.headers["content-type"].startswith("application/problem+json")


def test_csp_allows_every_external_resource_the_page_loads(client):
    """A resource the page links but the CSP blocks fails only in a browser; catch it here."""
    import re
    from urllib.parse import urlsplit

    html = client.get("/").text
    csp = client.get("/").headers["content-security-policy"]
    urls = re.findall(r'<(?:link|script)[^>]+(?:href|src)="(https?://[^"]+)"', html)
    for url in urls:
        if 'rel="preconnect"' in html and url.endswith(".com"):  # preconnect hints load nothing
            continue
        origin = "{0.scheme}://{0.netloc}".format(urlsplit(url))
        assert origin in csp, f"{origin} is linked from index.html but blocked by the CSP"
    if "fonts.googleapis.com/css" in html:
        assert "https://fonts.gstatic.com" in csp  # the stylesheet's font files come from here
