"""Restaurants a pilot needs (integration blueprint, phase 2): reports/pilot_sample_size.json.

    python scripts/pilot_sample_size.py                      # renewal 60% -> 70%, 5% two-sided, 80% power
    python scripts/pilot_sample_size.py --base 0.5 --target 0.6

The pilot randomises restaurants: half see TrueLift's forecast and weekly result, half do not.
Its primary outcome is the share of offers renewed at the end of the approval period. The usual
two-proportion formula gives the restaurants needed per arm:

    n = (z_a * sqrt(2 p (1 - p)) + z_b * sqrt(p1 (1 - p1) + p2 (1 - p2)))^2 / (p2 - p1)^2,  p = (p1 + p2) / 2

The baseline renewal rate is a placeholder: Eternal would replace it with the real one. Customers
choose between treated and untreated restaurants, so restaurant-level effects are contaminated by
competition; randomising whole localities avoids that and needs more restaurants (a design effect,
reported for a range of within-locality correlations).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from statistics import NormalDist

ROOT = Path(__file__).resolve().parents[1]


def per_arm(p1: float, p2: float, alpha: float = 0.05, power: float = 0.8) -> int:
    z_a, z_b = NormalDist().inv_cdf(1 - alpha / 2), NormalDist().inv_cdf(power)
    p = (p1 + p2) / 2
    n = (z_a * math.sqrt(2 * p * (1 - p)) + z_b * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2 / (p2 - p1) ** 2
    return math.ceil(n)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", type=float, default=0.60, help="renewal share without TrueLift (placeholder)")
    ap.add_argument("--target", type=float, default=0.70, help="renewal share worth detecting with it")
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--power", type=float, default=0.80)
    ap.add_argument("--per-locality", type=int, default=50, help="restaurants per locality cluster")
    a = ap.parse_args()
    n = per_arm(a.base, a.target, a.alpha, a.power)
    clusters = {}
    for icc in (0.01, 0.05, 0.10):
        deff = 1 + (a.per_locality - 1) * icc
        clusters[f"icc_{icc:.2f}"] = {"design_effect": round(deff, 2), "restaurants_per_arm": math.ceil(n * deff)}
    out = {
        "outcome": "share of offers renewed at the end of the approval period",
        "unit": "restaurant",
        "renewal_without": a.base,
        "renewal_with": a.target,
        "alpha_two_sided": a.alpha,
        "power": a.power,
        "restaurants_per_arm": n,
        "restaurants_total": 2 * n,
        "if_whole_localities_are_randomised": {"restaurants_per_locality": a.per_locality, **clusters},
        "note": "The baseline renewal share is a placeholder until Eternal supplies the real one.",
    }
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports/pilot_sample_size.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
