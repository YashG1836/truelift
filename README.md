# TrueLift

Restaurant discounts on Zomato are judged by the orders that **use** them, not the orders they
**create**. TrueLift forecasts, targets and measures each restaurant-funded offer by the extra
orders and profit it creates, inside Zomato's existing offer flow (the owner's OTP approval).

Team Banana (IIT Gandhinagar): Yash Goyal, Bhavay Goyal, Kshitish Madbhavi.
Full write-up: `TrueLift_Round2_Plan.md`. Working log: `LOG.md`.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build_restaurants.py   # needs data/raw/zomato_blr/zomato.csv (see below)
.venv/bin/python scripts/run_pipeline.py        # ~6 min: simulate, train, evaluate -> reports/
.venv/bin/uvicorn truelift.api:app --port 8000  # open http://localhost:8000
.venv/bin/python -m pytest -q                   # tests
.venv/bin/python scripts/export_static.py 142 283 97  # static demo -> site/ (GitHub Pages)
.venv/bin/python scripts/validate_mtlift.py      # optional: check on Meituan's real coupon data
```

## What is where

| Path | What it does |
|---|---|
| `truelift/economics.py` | Money of one order: commission, GST, food cost, discount, who funds it |
| `truelift/sim.py` | Simulated Bengaluru market where every discount's true effect is known |
| `truelift/model.py` | Uplift model: chance of ordering with and without an offer; Qini check |
| `truelift/engine.py` | The four decisions: quote, serve, funding, weekly measurement |
| `truelift/api.py` | Service with Zomato-style hooks, plus the demo endpoints |
| `truelift/static/` | Partner-app prototype, "Inside Zomato" panel, evidence and money pages |
| `scripts/` | Build the restaurant list, run the evaluation pipeline, export the static site, check on MT-LIFT |
| `tests/` | Checks for the maths, the simulator, the measurement and the API |
| `reports/` | Evaluation results (JSON, CSV) |
| `docs/` | Round 1 problem statement (PDF) |

## Data

- `data/raw/zomato_blr/zomato.csv`: Kaggle "Zomato Bangalore Restaurants" (2019). We use public
  listing fields only (name, locality, cuisines, cost for two, rating, votes) for 300 restaurants.
- Optional `data/raw/mt_lift/`: Meituan's MT-LIFT randomised coupon dataset (5.5M rows). Its
  Google Drive link needs a sign-in, so download it by hand from github.com/MTDJDSP/MT-LIFT.
- Customers are synthetic. No real customer data is used anywhere.
