"""Build the simulator's restaurant list from the public Zomato Bangalore dataset.

Input : data/raw/zomato_blr/zomato.csv (Kaggle "Zomato Bangalore Restaurants", 2019 snapshot)
Output: data/processed/restaurants.csv (300 delivery restaurants, 6 localities x 50)

Only public listing fields are used: name, locality, cuisines, cost for two, rating, votes.
Everything else about these restaurants (customers, orders, profits) is simulated, and the UI says so.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]  # paths work from any working directory (audit TL-034)
RAW = ROOT / "data/raw/zomato_blr/zomato.csv"
OUT = ROOT / "data/processed/restaurants.csv"
LOCALITIES = ["Koramangala 5th Block", "HSR", "BTM", "Indiranagar", "Jayanagar", "Whitefield"]
PER_LOCALITY = 50
SEED = 2026


def main() -> int:
    cols = ["name", "online_order", "rate", "votes", "location", "cuisines", "approx_cost(for two people)"]
    df = pd.read_csv(RAW, usecols=cols)
    df = df[df["online_order"] == "Yes"].copy()
    df["cost_for_two"] = pd.to_numeric(
        df["approx_cost(for two people)"].astype(str).str.replace(",", ""), errors="coerce"
    )
    df["rating"] = pd.to_numeric(df["rate"].astype(str).str.extract(r"(\d\.\d)")[0], errors="coerce")
    df = df.dropna(subset=["cost_for_two", "rating", "cuisines", "location"])
    df = df[(df["votes"] >= 30) & df["cost_for_two"].between(150, 1500)]
    # The raw file repeats a restaurant once per listing type; keep its most-voted row.
    df = df.sort_values("votes", ascending=False).drop_duplicates(["name", "location"])
    df = df[df["location"].isin(LOCALITIES)]

    rng = np.random.default_rng(SEED)
    parts = []
    for loc in LOCALITIES:
        sub = df[df["location"] == loc]
        if len(sub) < PER_LOCALITY:
            raise SystemExit(f"{loc}: only {len(sub)} restaurants after filtering")
        parts.append(sub.iloc[rng.choice(len(sub), PER_LOCALITY, replace=False)])
    out = pd.concat(parts).reset_index(drop=True)
    out["cuisines"] = out["cuisines"].str.split(",").str[:2].str.join(",").str.strip()
    out.insert(0, "restaurant_id", np.arange(len(out)))
    out = out.rename(columns={"location": "locality"})
    out[["restaurant_id", "name", "locality", "cuisines", "cost_for_two", "rating", "votes"]].to_csv(OUT, index=False)
    print(f"wrote {OUT}: {len(out)} restaurants")
    print(out.groupby("locality")[["cost_for_two", "rating", "votes"]].median())
    return 0


if __name__ == "__main__":
    sys.exit(main())
