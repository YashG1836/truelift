"""Build the static demo (no server needed): site/ = the UI + every answer the UI can ask for.

    python scripts/export_static.py [restaurant_id ...]      # default: the demo restaurant
    python scripts/export_static.py --assets                 # refresh only the UI files of site/

For each chosen restaurant and every design the create screen can produce, this calls the real
TrueLift service in-process and saves its answers: the quote, who sees the discount, and the offer
after up to four simulated weeks. The page replays them. The design options come from the
restaurant's card, the same function the page reads, and a self-check fails the export if any
file the page can request is missing (audit TL-002). Needs the model bundle.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from truelift.api import app, get_state  # noqa: E402

SITE = Path(os.environ.get("TRUELIFT_SITE_DIR", ROOT / "site"))
AUDIENCES = ("all", "new_to_restaurant", "lapsed", "targeted")


def designs_for(opts: dict) -> list[dict]:
    """Every design the create screen can produce, from the card's design options."""
    out = [
        {"discount": 0, "min_order": 0, "audience": "all", "offpeak_only": False, "reward": r, "zomato_share": 0}
        for r in (0, opts["reward"])
    ]
    for d in opts["depths"]:
        for m in (0, opts["min_order"]):
            for a in AUDIENCES:
                for o in (False, True):
                    for r in (0, opts["reward"]):
                        out.append(
                            {
                                "discount": d,
                                "min_order": m,
                                "audience": a,
                                "offpeak_only": o,
                                "reward": r,
                                "zomato_share": 0,
                            }
                        )
    return out


def key(d: dict) -> str:
    """File name of a design's answers; identical to dkey() in app.js."""
    if not d["discount"] > 0:
        return f"0-0-all-0-{round(d['reward'])}"
    parts = (
        round(d["discount"]),
        round(d["min_order"]),
        d["audience"],
        int(bool(d["offpeak_only"])),
        round(d["reward"]),
    )
    return "-".join(str(x) for x in parts)


def write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")


def export_restaurant(rid: int) -> list:
    """All designs for one restaurant; runs in its own process (its own copy of the service)."""
    c = TestClient(app)
    h = {"X-Session": f"export{rid}"}
    data = SITE / "data"
    timings = []
    card = c.get(f"/api/v1/restaurants/{rid}").json()
    write(data / str(rid) / "card.json", card)
    ds = designs_for(card["design_options"])
    t0 = time.time()
    for i, d in enumerate(ds):
        c.post("/api/v1/reset", json={}, headers=h)
        body = {"restaurant_id": rid, "design": d}
        t = time.perf_counter()
        quote = c.post("/api/v1/quote", json=body, headers=h)
        timings.append(("quote", (time.perf_counter() - t) * 1000))
        if quote.status_code != 200:
            raise RuntimeError(f"restaurant {rid} {key(d)}: quote failed {quote.status_code} {quote.text[:200]}")
        item = {"quote": quote.json()}
        if d["discount"] > 0:
            off = c.post("/api/v1/offers", json=body, headers=h).json()
            c.post(f"/api/v1/offers/{off['offer_id']}/approve", json={"otp": off["demo_otp"]}, headers=h)
            item["customers"] = c.post("/api/v1/customers", json=body, headers=h).json()
            cust = item["customers"]["customers"]
            if cust:  # time a real decision: the offer is active here (audit TL-005)
                t = time.perf_counter()
                c.get("/api/v1/serve", params={"restaurant_id": rid, "customer_id": cust[0]["customer_id"]}, headers=h)
                timings.append(("serve", (time.perf_counter() - t) * 1000))
            view = None
            for w in range(1, 5):
                view = c.post(f"/api/v1/offers/{off['offer_id']}/run_week", params={"week": w}, headers=h).json()
                if view["status"] != "active":
                    break
            item["offer"] = view
        else:
            item["customers"] = c.post("/api/v1/customers", json=body, headers=h).json()
        write(data / str(rid) / f"{key(d)}.json", item)
        if i % 20 == 0:
            print(f"restaurant {rid}: {i + 1}/{len(ds)} designs ({time.time() - t0:.0f}s)", flush=True)
    return timings


def self_check(rids: list[int]) -> list[str]:
    """Every file the page can request for these restaurants must exist."""
    missing = []
    for rid in rids:
        card_path = SITE / "data" / str(rid) / "card.json"
        if not card_path.exists():
            missing.append(str(card_path))
            continue
        card = json.loads(card_path.read_text(encoding="utf-8"))
        for d in designs_for(card["design_options"]):
            f = SITE / "data" / str(rid) / f"{key(d)}.json"
            if not f.exists():
                missing.append(str(f.relative_to(SITE)))
    return missing


def write_assets() -> None:
    """UI files: the same static files as the service, with the page pointed at data/."""
    shutil.copytree(ROOT / "truelift/static", SITE / "static", dirs_exist_ok=True)
    html = (ROOT / "truelift/static/index.html").read_text(encoding="utf-8")
    html = html.replace(
        '<script src="/static/app.js"></script>',
        '<script src="static/static-mode.js"></script>\n<script src="static/app.js"></script>',
    )
    html = html.replace('href="/static/', 'href="static/')
    (SITE / "index.html").write_text(html, encoding="utf-8")
    (SITE / "static" / "static-mode.js").write_text('window.TRUELIFT_STATIC = "data/";\n', encoding="utf-8")
    (SITE / ".nojekyll").write_text("", encoding="utf-8")


def main() -> int:
    from concurrent.futures import ProcessPoolExecutor

    if sys.argv[1:] == ["--assets"]:
        write_assets()
        print(f"UI files refreshed in {SITE}")
        return 0
    c = TestClient(app)
    rids = [int(a) for a in sys.argv[1:]] or [get_state().demo_restaurant]
    if SITE.exists():
        shutil.rmtree(SITE)
    write_assets()
    data = SITE / "data"
    allr = c.get("/api/v1/restaurants").json()
    write(
        data / "restaurants.json",
        {"demo_restaurant": rids[0], "restaurants": [r for r in allr["restaurants"] if r["restaurant_id"] in rids]},
    )
    write(data / "evidence.json", c.get("/api/v1/evidence").json())
    write(data / "example.json", c.get("/api/v1/example").json())
    write(data / "config.json", c.get("/api/v1/config").json())
    workers = int(os.environ.get("TRUELIFT_EXPORT_WORKERS", "4"))
    with ProcessPoolExecutor(max_workers=max(1, min(len(rids), workers))) as pool:
        timings = [t for part in pool.map(export_restaurant, rids) for t in part]

    def med(name):
        xs = sorted(t for n, t in timings if n == name)
        return xs[len(xs) // 2] if xs else None

    write(
        data / "calls.json",
        {
            "calls": [
                {"hook": "quote (forecast + 34 versions compared)", "ms": round(med("quote"), 1)},
                {"hook": "serve (one customer opens the menu, offer active)", "ms": round(med("serve") or 0, 2)},
            ]
        },
    )
    missing = self_check(rids)
    if missing:
        print(f"EXPORT FAILED: {len(missing)} files the page can request are missing, e.g. {missing[:5]}")
        return 1
    print(f"site written to {SITE}; self-check passed for {len(rids)} restaurants")
    return 0


if __name__ == "__main__":
    sys.exit(main())
