"""Build the static demo for GitHub Pages (no server needed): site/ = UI + precomputed responses.

    .venv/bin/python scripts/export_static.py [restaurant_id ...]

For each chosen restaurant and every design the screen's buttons can make, this calls the real
TrueLift service in-process and saves its answers: the quote, who sees the discount, and the
offer after up to 4 simulated weeks. The static UI replays them. Needs data/processed/model.pkl.
"""
from __future__ import annotations

import json
import math
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from truelift.api import app, st  # noqa: E402

SITE = ROOT / "site"


def designs_for(aov: float) -> list[dict]:
    """Every design the create screen can produce (same rounding as app.js and Engine.design_grid)."""
    depths = sorted({max(20, round(aov * f / 10) * 10) for f in (0.10, 0.15, 0.20, 0.25)})
    mov = math.ceil(aov * 1.15 / 50) * 50 - 1
    rw = max(5, round(aov * 0.05 / 5) * 5)
    out = [{"discount": 0, "min_order": 0, "audience": "all", "offpeak_only": False, "reward": r, "zomato_share": 0}
           for r in (0, rw)]
    for d in depths:
        for m in (0, mov):
            for a in ("all", "new_to_restaurant", "lapsed", "targeted"):
                for o in (False, True):
                    for r in (0, rw):
                        out.append({"discount": d, "min_order": m, "audience": a, "offpeak_only": o,
                                    "reward": r, "zomato_share": 0})
    return out


def key(d: dict) -> str:
    return f"{round(d['discount'])}-{round(d['min_order'])}-{d['audience']}-{int(bool(d['offpeak_only']))}-{round(d['reward'])}"


def write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":")))


def export_restaurant(rid: int) -> list:
    """All designs for one restaurant; runs in its own process (its own copy of the service)."""
    c = TestClient(app)
    data = SITE / "data"
    timings = []
    card = c.get(f"/api/restaurants/{rid}").json()
    write(data / str(rid) / "card.json", card)
    ds = designs_for(card["aov"])
    t0 = time.time()
    for i, d in enumerate(ds):
        c.post("/api/reset", json={})
        body = {"restaurant_id": rid, "design": d}
        t = time.perf_counter()
        item = {"quote": c.post("/api/quote", json=body).json()}
        timings.append(("quote", (time.perf_counter() - t) * 1000))
        if d["discount"] > 0:
            off = c.post("/api/offers", json=body).json()
            c.post(f"/api/offers/{off['offer_id']}/approve", json={"otp": off["demo_otp"]})
            item["customers"] = c.post("/api/customers", json=body).json()
            view = None
            for _ in range(4):
                view = c.post(f"/api/offers/{off['offer_id']}/run_week").json()
                if view["status"] != "active":
                    break
            item["offer"] = view
            cust = item["customers"]["customers"]
            if cust:
                t = time.perf_counter()
                c.get("/api/serve", params={"restaurant_id": rid, "customer_id": cust[0]["customer_id"]})
                timings.append(("serve", (time.perf_counter() - t) * 1000))
        else:
            item["customers"] = c.post("/api/customers", json=body).json()
        write(data / str(rid) / f"{key(d)}.json", item)
        if i % 20 == 0:
            print(f"restaurant {rid}: {i + 1}/{len(ds)} designs ({time.time() - t0:.0f}s)", flush=True)
    return timings


def main() -> int:
    from concurrent.futures import ProcessPoolExecutor
    c = TestClient(app)
    rids = [int(a) for a in sys.argv[1:]] or [st().demo_restaurant]
    if SITE.exists():
        shutil.rmtree(SITE)
    shutil.copytree(ROOT / "truelift/static", SITE / "static")
    html = (ROOT / "truelift/static/index.html").read_text()
    html = html.replace('<script src="/static/app.js"></script>',
                        '<script>window.TRUELIFT_STATIC = "data/";</script>\n<script src="static/app.js"></script>')
    html = html.replace('href="/static/style.css"', 'href="static/style.css"')
    (SITE / "index.html").write_text(html)
    (SITE / ".nojekyll").write_text("")
    data = SITE / "data"
    allr = c.get("/api/restaurants").json()
    write(data / "restaurants.json", {"demo_restaurant": rids[0],
                                      "restaurants": [r for r in allr["restaurants"] if r["restaurant_id"] in rids]})
    ev = c.get("/api/evidence").json()
    for part in ev.values():  # keep real restaurant names out of the public site
        if isinstance(part, dict) and isinstance(part.get("demo_restaurant"), dict):
            part["demo_restaurant"].pop("name", None)
    write(data / "evidence.json", ev)
    write(data / "example.json", c.get("/api/example").json())
    with ProcessPoolExecutor(max_workers=len(rids)) as pool:
        timings = [t for part in pool.map(export_restaurant, rids) for t in part]
    med = lambda name: sorted(t for n, t in timings if n == name)[len([t for n, t in timings if n == name]) // 2]  # noqa: E731
    write(data / "calls.json", {"calls": [
        {"hook": "quote (forecast + 34 versions compared)", "ms": round(med("quote"), 1)},
        {"hook": "serve (one customer opens the menu)", "ms": round(med("serve"), 1)},
    ]})
    print(f"site written to {SITE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
