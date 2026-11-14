"""Write the results tables in the README and the plan from reports/, so a number in a document can
never drift from the file it comes from (audit A07 R5). Each table sits between markers:

    <!-- BEGIN:results-table -->
    ...generated...
    <!-- END:results-table -->

    python scripts/render_tables.py          # rewrite the marked tables
    python scripts/render_tables.py --check  # exit 1 if any marked table is out of date (CI)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = [ROOT / "README.md", ROOT / "TrueLift_Round2_Plan.md"]
COLS = (
    ("today_blanket", "Today: same discount for everyone"),
    ("rule_new_customers", "Rule: new customers only"),
    ("truelift", "TrueLift"),
)


def lakh(x: float, sign: bool = False) -> str:
    s = "−" if x < 0 else ("+" if sign else "")
    return f"{s}₹{abs(x) / 1e5:.2f} lakh"


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


TABLES = {"results-table": results_table, "scenario-table": scenario_table}


def render(text: str, ev: dict) -> str:
    for name, fn in TABLES.items():
        # the region may be empty (a fresh marker pair) or hold an older table
        pat = re.compile(rf"(<!-- BEGIN:{name} -->\n)(?:.*?\n)??(<!-- END:{name} -->)", re.S)
        text = pat.sub(lambda m, fn=fn: m.group(1) + fn(ev) + "\n" + m.group(2), text)
    return text


def main() -> int:
    check = "--check" in sys.argv[1:]
    ev = json.loads((ROOT / "reports/evaluation.json").read_text(encoding="utf-8"))
    stale = []
    for doc in DOCS:
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
