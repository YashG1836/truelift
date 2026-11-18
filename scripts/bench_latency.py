"""Latency of the live service, measured end to end over HTTP (audit TL-005, TL-026, A16).

    python scripts/bench_latency.py               # starts the service on a free port -> reports/latency.json
    python scripts/bench_latency.py --url http://127.0.0.1:8000   # measure a service that is already running

What is timed: 1,000 serving decisions (hook 2: a customer opens the menu), one after another and
from 8 threads at once, and 100 quotes (hook 1: the forecast for an offer and its best version,
which compares about 34 versions). Client-side times include HTTP; the service also reports its own
handling time per decision. The report records the hardware, because these numbers depend on it.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DESIGN = {"discount": 60, "min_order": 0, "audience": "targeted", "offpeak_only": False, "reward": 0, "zomato_share": 0}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def summary(ms: list[float]) -> dict:
    a = np.asarray(ms, float)
    return {
        "calls": int(len(a)),
        "p50_ms": round(float(np.percentile(a, 50)), 2),
        "p95_ms": round(float(np.percentile(a, 95)), 2),
        "p99_ms": round(float(np.percentile(a, 99)), 2),
        "mean_ms": round(float(a.mean()), 2),
        "max_ms": round(float(a.max()), 2),
    }


def hardware() -> dict:
    return {
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "logical_cpus": os.cpu_count(),
        "python": platform.python_version(),
    }


def wait_ready(url: str, timeout: float = 300.0) -> None:
    t = time.time()
    while time.time() - t < timeout:
        try:
            if httpx.get(f"{url}/readyz", timeout=5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise SystemExit(f"service at {url} not ready after {timeout:.0f}s")


def bench(url: str, serves: int, quotes: int, threads: int) -> dict:
    h = {"X-Session": uuid.uuid4().hex[:16]}
    with httpx.Client(base_url=url, headers=h, timeout=60) as c:
        rid = c.get("/api/v1/restaurants").json()["demo_restaurant"]
        off = c.post("/api/v1/offers", json={"restaurant_id": rid, "design": DESIGN}).json()
        c.post(f"/api/v1/offers/{off['offer_id']}/approve", json={"otp": off["demo_otp"]}).raise_for_status()
        cust = [
            x["customer_id"]
            for x in c.post("/api/v1/customers", json={"restaurant_id": rid, "design": DESIGN}).json()["customers"]
        ]

        def one_serve(i: int, client: httpx.Client) -> tuple[float, float]:
            t = time.perf_counter()
            r = client.get("/api/v1/serve", params={"restaurant_id": rid, "customer_id": cust[i % len(cust)]})
            r.raise_for_status()
            return (time.perf_counter() - t) * 1000, float(r.json().get("latency_ms") or 0.0)

        for i in range(20):  # warm-up: connections, caches
            one_serve(i, c)
        seq = [one_serve(i, c) for i in range(serves)]

        def worker(k: int) -> list[tuple[float, float]]:
            with httpx.Client(base_url=url, headers=h, timeout=60) as cc:
                return [one_serve(k * 1000 + i, cc) for i in range(serves // threads)]

        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=threads) as pool:
            par = [x for part in pool.map(worker, range(threads)) for x in part]
        wall = time.perf_counter() - t0

        q_ms = []
        for i in range(quotes):
            d = {**DESIGN, "discount": [40, 50, 60, 80][i % 4]}
            t = time.perf_counter()
            c.post("/api/v1/quote", json={"restaurant_id": rid, "design": d}).raise_for_status()
            q_ms.append((time.perf_counter() - t) * 1000)
    return {
        "serve_sequential": {**summary([a for a, _ in seq]), "server_side": summary([b for _, b in seq])},
        f"serve_{threads}_threads": {
            **summary([a for a, _ in par]),
            "server_side": summary([b for _, b in par]),
            "throughput_per_second": round(len(par) / wall, 1),
        },
        "quote_sequential": summary(q_ms),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--url", help="measure a running service instead of starting one")
    ap.add_argument("--serves", type=int, default=1000)
    ap.add_argument("--quotes", type=int, default=100)
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--out", type=Path, default=ROOT / "reports")
    args = ap.parse_args()
    proc = None
    url = args.url
    if not url:
        port = free_port()
        url = f"http://127.0.0.1:{port}"
        env = {**os.environ, "TRUELIFT_LOG_JSON": "0", "PYTHONIOENCODING": "utf-8"}
        cmd = [sys.executable, "-m", "uvicorn", "truelift.api:app", "--port", str(port), "--log-level", "warning"]
        proc = subprocess.Popen(cmd, cwd=ROOT, env=env)
    try:
        wait_ready(url)
        res = bench(url, args.serves, args.quotes, args.threads)
    finally:
        if proc:
            proc.terminate()
            proc.wait(timeout=30)
    report = {"measured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "hardware": hardware(), **res}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "latency.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
