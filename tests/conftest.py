"""Shared fixtures. Every test runs on a fresh clone: the API tests use a small model trained once
per test session, never the git-ignored or committed full model (audit A12 Q1)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SMALL_CUSTOMERS = 300  # per locality: 1,800 customers, trains in about two seconds


@pytest.fixture(scope="session")
def restaurants() -> pd.DataFrame:
    return pd.read_csv(ROOT / "data/processed/restaurants.csv")


@pytest.fixture(scope="session")
def small_trained(restaurants):
    """History, model and calibration for a small market (same code as the pipeline)."""
    from truelift.economics import Terms
    from truelift.sim import Config, Market
    from truelift.training import train

    return train(Market(restaurants, Config(customers_per_locality=SMALL_CUSTOMERS), Terms()))


@pytest.fixture(scope="session")
def model_dir(small_trained, tmp_path_factory) -> Path:
    from truelift.model import save_bundle

    d = tmp_path_factory.mktemp("model")
    save_bundle(small_trained.bundle(233, version="test-small"), d / "model.pkl")
    return d


@pytest.fixture(scope="session")
def service_env(model_dir):
    """Point the service at the small model; restore the environment afterwards."""
    keys = {
        "TRUELIFT_MODEL": str(model_dir / "model.pkl"),
        "TRUELIFT_CACHE_DIR": str(model_dir),
        "TRUELIFT_DB": ":memory:",
        "TRUELIFT_LOG_JSON": "0",
    }
    old = {k: os.environ.get(k) for k in keys}
    os.environ.update(keys)
    from truelift import api

    api.reset_state()
    yield model_dir
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    api.reset_state()


@pytest.fixture(scope="session")
def client(service_env):
    from fastapi.testclient import TestClient

    from truelift.api import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def session_headers() -> dict:
    """A fresh demo session for one test, so tests never see each other's offers."""
    return {"X-Session": uuid.uuid4().hex[:16]}


@pytest.fixture
def state(client):
    """The live service state (some tests rebuild it, so never cache it across tests)."""
    from truelift.api import get_state

    return get_state()


@pytest.fixture(scope="session")
def quick_report(tmp_path_factory) -> dict:
    """The quick pipeline's evaluation.json, run once per test session (slow tests only)."""
    import json
    import subprocess
    import sys

    out = tmp_path_factory.mktemp("quick_pipeline")
    cmd = [
        sys.executable,
        str(ROOT / "scripts/run_pipeline.py"),
        "--quick",
        "--out",
        str(out),
        "--model-out",
        str(out / "model.pkl"),
    ]
    subprocess.run(cmd, check=True, cwd=ROOT, capture_output=True)
    return json.loads((out / "evaluation.json").read_text(encoding="utf-8"))


DESIGN = {"discount": 60, "min_order": 0, "audience": "targeted", "offpeak_only": False, "reward": 0, "zomato_share": 0}


def approved_offer(client, headers, rid: int = 233, design: dict | None = None) -> dict:
    """Create and approve an offer; returns the offer view."""
    body = {"restaurant_id": rid, "design": design or DESIGN}
    off = client.post("/api/v1/offers", json=body, headers=headers)
    assert off.status_code == 201, off.text
    off = off.json()
    view = client.post(f"/api/v1/offers/{off['offer_id']}/approve", json={"otp": off["demo_otp"]}, headers=headers)
    assert view.status_code == 200, view.text
    return view.json()
