"""Load test for the live service (audit WP-40 P4): many demo visitors at once.

    python tasks.py serve                       # in one terminal
    uv run locust -f tests/load/locustfile.py --headless -u 50 -r 10 -t 60s --host http://127.0.0.1:8000 \\
        --csv reports/load --html reports/load.html

Each simulated visitor is an owner in their own demo session: quote an offer, approve it with the
demo OTP, then many customers open the menu (the serving hook, the hot path), and now and then a
week is simulated (the slow path). The mix is weighted toward serving, as real traffic would be.
"""

from __future__ import annotations

import random
import uuid

from locust import HttpUser, between, task

DESIGN = {"discount": 60, "min_order": 0, "audience": "targeted", "offpeak_only": False, "reward": 0, "zomato_share": 0}


class Owner(HttpUser):
    wait_time = between(0.05, 0.3)

    def on_start(self) -> None:
        self.client.headers["X-Session"] = uuid.uuid4().hex[:16]
        self.rid = self.client.get("/api/v1/restaurants", name="restaurants").json()["demo_restaurant"]
        off = self.client.post(
            "/api/v1/offers", json={"restaurant_id": self.rid, "design": DESIGN}, name="offers"
        ).json()
        self.oid = off["offer_id"]
        self.client.post(f"/api/v1/offers/{self.oid}/approve", json={"otp": off["demo_otp"]}, name="approve")
        body = {"restaurant_id": self.rid, "design": DESIGN}
        self.customers = [
            c["customer_id"] for c in self.client.post("/api/v1/customers", json=body).json()["customers"]
        ]
        self.weeks = 0

    @task(50)
    def serve(self) -> None:
        cid = random.choice(self.customers)
        self.client.get("/api/v1/serve", params={"restaurant_id": self.rid, "customer_id": cid}, name="serve")

    @task(5)
    def quote(self) -> None:
        d = {**DESIGN, "discount": random.choice([40, 50, 60, 80])}
        self.client.post("/api/v1/quote", json={"restaurant_id": self.rid, "design": d}, name="quote")

    @task(1)
    def run_week(self) -> None:
        if self.weeks < 4:
            self.client.post(f"/api/v1/offers/{self.oid}/run_week", name="run_week")
            self.weeks += 1
