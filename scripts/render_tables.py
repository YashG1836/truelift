"""Write the results tables in the documents from reports/, so a number in a document can never drift
from the file it comes from (audit A07 R5). Each table sits between markers:

    <!-- BEGIN:results-table -->
    ...generated...
    <!-- END:results-table -->

    python scripts/render_tables.py          # rewrite the marked tables
    python scripts/render_tables.py --check  # exit 1 if any marked table is out of date (CI)

reports/evaluation.md holds every table in one place (audit A07 R1).
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = [
    ROOT / "README.md",
    ROOT / "docs/method_and_evidence.md",
    ROOT / "docs/privacy_and_fairness.md",
    ROOT / ".claude/context/STATE.md",
    ROOT / "reports/evaluation.md",
]
COLS = (
    ("today_blanket", "Today: same discount for everyone"),
    ("rule_new_customers", "Rule: new customers only"),
    ("truelift", "TrueLift"),
)


def lakh(x: float, sign: bool = False) -> str:
    s = "−" if x < 0 else ("+" if sign else "")
    return f"{s}₹{abs(x) / 1e5:.2f} lakh"


def inr(x: float, sign: bool = False) -> str:
    v = round(x)
    s = "−" if v < 0 else ("+" if sign and v > 0 else "")
    return f"{s}₹{abs(v):,}"


def pct(x: float) -> str:
    """Whole percent, halves rounded up as the page rounds them (JavaScript Math.round)."""
    return f"{math.floor(100 * x + 0.5)}%".replace("-", "−")


def results_table(ev: dict) -> str:
    p = ev["main"]["policies"]
    rows = [
        ("Offers that pay for themselves", lambda d: f"{d['offers_that_pay']} of {d['restaurants_with_offer']}"),
        ("Offers that lose money", lambda d: str(d["offers_that_lose"])),
        ("Restaurants' profit from their own offers", lambda d: lakh(d["own_offer_profit_effect"], True)),
        ("Restaurant profit vs no offers (market)", lambda d: lakh(d["restaurant_profit_change"], True)),
        ("Discount given", lambda d: lakh(d["customer_savings"])),
        ("Zomato commission vs no offers", lambda d: lakh(d["zomato_commission_change"], True)),
    ]
    best = {
        "Offers that pay for themselves": max(COLS, key=lambda c: p[c[0]]["offers_that_pay"])[0],
        "Offers that lose money": min(COLS, key=lambda c: p[c[0]]["offers_that_lose"])[0],
        "Restaurants' profit from their own offers": max(COLS, key=lambda c: p[c[0]]["own_offer_profit_effect"])[0],
        "Restaurant profit vs no offers (market)": max(COLS, key=lambda c: p[c[0]]["restaurant_profit_change"])[0],
        "Discount given": min(COLS, key=lambda c: p[c[0]]["customer_savings"])[0],
        "Zomato commission vs no offers": max(COLS, key=lambda c: p[c[0]]["zomato_commission_change"])[0],
    }
    out = ["| | " + " | ".join(name for _, name in COLS) + " |", "|---|" + "---|" * len(COLS)]
    for label, f in rows:
        cells = [f"**{f(p[k])}**" if best[label] == k else f(p[k]) for k, _ in COLS]
        out.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def scenario_table(ev: dict) -> str:
    sc = [
        ("Customers 30% less price-sensitive", ev.get("less_price_sensitive")),
        ("Base case", ev["main"]),
        ("Customers 30% more price-sensitive", ev.get("more_price_sensitive")),
        ("Commission on the price before the discount", ev.get("pre_discount_commission")),
    ]
    trio_head = "today / rule / TrueLift"
    heads = ("Offers that pay", "Own-offer profit", "Restaurant profit vs no offers", "Zomato commission vs no offers")
    out = ["| Scenario | " + " | ".join(f"{h}: {trio_head}" for h in heads) + " |", "|---|---|---|---|---|"]
    for label, s in sc:
        if not s:
            continue
        p = s["policies"]
        trio = [p[k] for k, _ in COLS]
        out.append(
            f"| {label} | "
            + " / ".join(str(d["offers_that_pay"]) for d in trio)
            + " | "
            + " / ".join(lakh(d["own_offer_profit_effect"]) for d in trio)
            + " | "
            + " / ".join(lakh(d["restaurant_profit_change"], True) for d in trio)
            + " | "
            + " / ".join(lakh(d["zomato_commission_change"], True) for d in trio)
            + " |"
        )
    return "\n".join(out)


def measurement_table(ev: dict) -> str:
    m = ev["main"]["measurement"]
    out = [
        "| After | Truth inside the 80% range | Average error: control group only | Model only | "
        'TrueLift combined | "Keep" verdicts truly positive |',
        "|---|---|---|---|---|---|",
    ]
    for w in (1, 2, 4):
        r = m[f"after_{w}_weeks"]
        keeps = r["verdicts"].get("keep", 0)
        right = f"{r['said_keep_and_truly_positive']} of {keeps}" if keeps else "–"
        out.append(
            f"| {w} week{'s' if w > 1 else ''} | {pct(r['coverage_80'])} | {inr(r['mae_own_holdout_only'])} | "
            f"{inr(r['mae_model_only'])} | {inr(r['mae_combined'])} | {right} |"
        )
    return "\n".join(out)


def fairness_table(ev: dict) -> str:
    main = ev["main"]
    f, p = main["fairness"], main["policies"]
    rows = (
        ("today_blanket", "Today: same discount for everyone", p["today_blanket"]),
        ("truelift", "TrueLift", p["truelift"]),
        (
            "brand_pack_for_regulars",
            "TrueLift + Brand Pack reward for regulars",
            f["mitigations"]["brand_pack_for_regulars"],
        ),
        (
            "regulars_always_eligible",
            "TrueLift, regulars always eligible",
            f["mitigations"]["regulars_always_eligible"],
        ),
        (
            "random_20pct_also_shown",
            "TrueLift + a random 20% of others shown",
            f["mitigations"]["random_20pct_also_shown"],
        ),
    )
    out = [
        "| Policy | Regulars offered a saving | Others offered a saving | Loyalty gap (points) | "
        "Restaurants' profit from their own offers | Offers that pay |",
        "|---|---|---|---|---|---|",
    ]
    for key, name, money in rows:
        reg = f[key]["by_segment"]["regular"]
        gap = f[key]["loyalty_gap"]
        out.append(
            f"| {name} | {pct(reg['regular here']['share_of_visits_offered_a_saving'])} | "
            f"{pct(reg['not a regular']['share_of_visits_offered_a_saving'])} | "
            f"{'–' if gap is None else str(round(100 * gap)).replace('-', '−')} | "
            f"{lakh(money['own_offer_profit_effect'], True)} | "
            f"{money['offers_that_pay']} |"
        )
    return "\n".join(out)


def pct_offers_table(ev: dict) -> str:
    po = ev["main"]["percentage_offers"]
    names = {
        "usual": "Percentage up to the flat amount (cap reached from half the usual order)",
        "proportional": "15% off up to twice the flat amount (discount follows the bill)",
    }
    out = [
        "| Format | Rupees off per use, share of the flat amount | Offers that pay: blanket / TrueLift | "
        "Own-offer profit: blanket / TrueLift | Restaurant profit vs no offers (market): blanket / TrueLift | "
        "TrueLift forecast against truth |",
        "|---|---|---|---|---|---|",
    ]

    def row(label: str, share: float, b: dict, t: dict, ratio: float) -> str:
        return (
            f"| {label} | {pct(share)} | {b['offers_that_pay']} / {t['offers_that_pay']} | "
            f"{lakh(b['own_offer_profit_effect'], True)} / {lakh(t['own_offer_profit_effect'], True)} | "
            f"{lakh(b['restaurant_profit_change'], True)} / {lakh(t['restaurant_profit_change'], True)} | {ratio:.2f} |"
        )

    flat = ev["main"]["policies"]
    fc = ev["main"]["forecast"]["truelift_design_in_todays_market"]["ratio_forecast_to_truth"]
    out.append(row("Flat amount (as above)", 1.0, flat["today_blanket"], flat["truelift"], fc))
    for key, v in po.items():
        b, t = v["policies"]["today_blanket"], v["policies"]["truelift"]
        r = v["forecast"]["truelift_design_in_todays_market"]["ratio_forecast_to_truth"]
        out.append(row(names.get(key, key), v["discount_per_use_share_of_flat_amount"], b, t, r))
    return "\n".join(out)


RANKS = (("random", "Random"), ("response", "Likely to act anyway"), ("s_learner", "S-learner"))
RANKS += (("t_learner", "T-learner (TrueLift)"), ("x_learner", "X-learner"))


def realdata_table(_: dict) -> str:
    outcome = {"visit": "visits", "conversion": "purchases", "spend": "spend"}
    arm = {"ads": "ads", "womens_email": "women's e-mail", "mens_email": "men's e-mail"}
    out = [
        "| Dataset and outcome | " + " | ".join(n for _, n in RANKS) + " |",
        "|---|" + "---|" * len(RANKS),
    ]
    for name in ("criteo", "hillstrom"):
        f = ROOT / f"reports/uplift_validation_{name}.json"
        if not f.exists():
            continue
        R = json.loads(f.read_text(encoding="utf-8"))
        for r in R["results"]:
            cells = []
            for k, _ in RANKS:
                m = r["rankings"][k]["top30_share_of_total_lift"]
                lo, hi = m["interval_90"]
                cells.append(f"{pct(m['value'])} ({pct(lo)} to {pct(hi)})")
            label = f"{name.capitalize()}, {arm.get(r['arm'], r['arm'])}: {outcome.get(r['label'], r['label'])}"
            out.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def seeds_table(ev: dict) -> str:
    """Mean and spread over the market seeds: how much each result depends on the random draw."""
    sd = ev["seeds"]
    p = sd["policies"]
    n = len(sd["seeds"])

    def ms(d: dict, money: bool, signed: bool) -> str:
        if money:
            return f"{lakh(d['mean'], signed)} ± {abs(d['sd']) / 1e5:.2f}"
        return f"{d['mean']:.0f} ± {d['sd']:.0f}"

    rows = (
        ("Offers that pay for themselves", "offers_that_pay", False, False),
        ("Restaurants' profit from their own offers", "own_offer_profit_effect", True, True),
        ("Restaurant profit vs no offers (market)", "restaurant_profit_change", True, True),
        ("Zomato commission vs no offers", "zomato_commission_change", True, True),
        ("Discount given", "customer_savings", True, False),
    )
    out = [
        f"| Mean ± sd over {n} market seeds | " + " | ".join(name for _, name in COLS) + " |",
        "|---|" + "---|" * len(COLS),
    ]
    for label, key, money, signed in rows:
        out.append(f"| {label} | " + " | ".join(ms(p[k][key], money, signed) for k, _ in COLS) + " |")
    return "\n".join(out)


TABLES = {
    "results-table": results_table,
    "seeds-table": seeds_table,
    "scenario-table": scenario_table,
    "measurement-table": measurement_table,
    "fairness-table": fairness_table,
    "pct-table": pct_offers_table,
    "realdata-table": realdata_table,
}


def render(text: str, ev: dict) -> str:
    for name, fn in TABLES.items():
        if f"<!-- BEGIN:{name} -->" not in text:
            continue
        # the region may be empty (a fresh marker pair) or hold an older table
        pat = re.compile(rf"(<!-- BEGIN:{name} -->\n)(?:.*?\n)??(<!-- END:{name} -->)", re.S)
        text = pat.sub(lambda m, fn=fn: m.group(1) + fn(ev) + "\n" + m.group(2), text)
    return text


def main() -> int:
    check = "--check" in sys.argv[1:]
    ev = json.loads((ROOT / "reports/evaluation.json").read_text(encoding="utf-8"))
    stale = []
    for doc in DOCS:
        if not doc.exists():
            continue
        old = doc.read_text(encoding="utf-8")
        new = render(old, ev)
        if new != old:
            stale.append(doc.name)
            if not check:
                doc.write_text(new, encoding="utf-8", newline="\n")
    if check and stale:
        print(f"tables out of date in {', '.join(stale)}: run python scripts/render_tables.py")
        return 1
    print("tables " + ("checked" if check else f"written ({', '.join(stale) or 'no change'})"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
