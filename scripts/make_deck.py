"""Build the pitch deck, its speaker notes and the one-page summary from reports/ (decision D10).

    python scripts/make_deck.py           # docs/pitch/deck.html, one_page.html, speaker_notes.md
    python scripts/make_deck.py --pdf     # also TrueLift_deck.pdf, TrueLift_one_page.pdf and the
                                          # editable TrueLift_deck.pptx (uses tests/ui's Playwright:
                                          # cd tests/ui && npm ci && npx playwright install chromium)
    python scripts/make_deck.py --check   # exit 1 if a generated text file no longer matches reports/

Every number is computed from the reports with the claims ledger's namespace and formats
(scripts/check_claims.py) or taken from the generated tables (scripts/render_tables.py), so a slide
cannot say something the reports do not. Customers, orders and profits are simulated, and the
slides say so. Real restaurant names are left out of the deck (decision D5); the live demo keeps
them, labelled.

Open deck.html in a browser: arrow keys move, P presents one slide at a time, N shows the notes.
"""

from __future__ import annotations

import html
import io
import math
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_claims import fmt, half_up, namespace  # noqa: E402
from scripts.render_tables import fairness_table, lakh, measurement_table, seeds_table  # noqa: E402

OUT = ROOT / "docs" / "pitch"
DEMO_URL = "https://yashg1836.github.io/truelift/"
FONTS = "../../truelift/static/fonts"
NS = namespace()
EV = NS["ev"]

BLUE, GREY, GREY_DARK, INK, INK2, MUTED, LINE = (
    "#2a78d6",
    "#c9c7bf",
    "#8a877f",
    "#1c1c1c",
    "#4f4f4f",
    "#696969",
    "#e8e8e8",
)


def x(expr: str):
    """Evaluate an expression over the reports, exactly as the claims ledger does."""
    return eval(expr, {"__builtins__": {}, **NS})  # noqa: S307 (our own expressions, not input)


def v(expr: str, how: str = "plain") -> str:
    return fmt(x(expr), how)


def rs(value: float) -> str:
    """Rupees as the page writes them: whole rupees when whole, otherwise two decimals."""
    if abs(value - round(value)) < 0.005:
        return fmt(value, "inr")
    return f"₹{value:,.2f}"


def esc(s: str) -> str:
    return html.escape(s, quote=False)


# ------------------------------------------------------------------ the numbers on the slides
P = "ev.main.policies"
COLS = (
    ("today_blanket", "Same for everyone"),
    ("rule_new_customers", "New customers only"),
    ("truelift", "TrueLift"),
)
N_REST = x(f"{P}.today_blanket.restaurants_with_offer")
TL_PAY, TL_N = v(f"{P}.truelift.offers_that_pay"), v(f"{P}.truelift.restaurants_with_offer")
BL_PAY, RULE_PAY = v(f"{P}.today_blanket.offers_that_pay"), v(f"{P}.rule_new_customers.offers_that_pay")
NO_OFFER = v("ev.main.selection.no_offer_chosen")
LESS_DISCOUNT = v(f"{P}.today_blanket.customer_savings - {P}.truelift.customer_savings", "lakh2")
SEEDS = v(
    "len(ev.seeds.seeds) if ev.seeds.differences.truelift_minus_today_blanket.zomato_commission_change"
    ".same_sign_every_seed else -1",
    "word",
)
PLATFORM_SHARE = v("ev.main.zomato_ledger.platform_incremental_share_of_extra_orders.truelift", "pct0")
BL_ANYWAY = x(f"{P}.today_blanket.anyway_share_of_redemptions")
TL_ANYWAY = v(f"{P}.truelift.anyway_share_of_redemptions", "pct0")
FULL, DISC = NS["ex"].per_order_full, NS["ex"].per_order_discounted
BREAK_EVEN = v("100 * (1 - ex.per_order_discounted.restaurant_profit / ex.per_order_full.restaurant_profit)")
BREAK_EVEN_PRE = v("100 * (1 - pre.per_order_discounted.restaurant_profit / pre.per_order_full.restaurant_profit)")
COVERAGE = {w: v(f"ev.main.measurement.after_{w}_weeks.coverage_80", "pct0") for w in (1, 2, 4)}
KEEP = {
    w: (
        v(f"ev.main.measurement.after_{w}_weeks.said_keep_and_truly_positive"),
        v(f"ev.main.measurement.after_{w}_weeks.verdicts.keep"),
    )
    for w in (1, 4)
}
AA = v("ev.main.aa_test.lifetime_false_pause_4_looks", "pct1")
AA_BEFORE = v("ev.main.aa_test.lifetime_false_pause_4_looks_rule_before", "pct1")
CRITEO = {
    (o, r): v(f"criteo.results[{o}]['rankings']['{r}']['top30_share_of_total_lift']['value']", "pct0")
    for o in (0, 1)
    for r in ("t_learner", "response", "x_learner")
}
HILL_SPLITS = v(
    "min(sum(a > b for a, b in pair) for pair in [zip(hill.results[0]['rankings'][m]['top30_share_of_total_lift']"
    "['splits'], hill.results[0]['rankings']['response']['top30_share_of_total_lift']['splits']) "
    "for m in ('s_learner', 't_learner', 'x_learner')])",
    "word",
)
INFLATION = v("ev.main.selection.forecast_advantage_total / ev.main.selection.true_advantage_total", "word")
TRULY_BETTER = v("ev.main.selection.share_truly_better_than_owner", "pct0")
DRAWS_BIAS = v("exp('holdout_draws').mean_error_rs", "inr")
PILOT_ARM, PILOT_TOTAL = v("pilot.restaurants_per_arm", "int"), v("pilot.restaurants_total", "int")
CONTROL_COST = v("ev.main.zomato_ledger.control_group_cost_truelift.profit_forgone_a_week", "inr")
CONTROL_ORDERS = v("ev.main.zomato_ledger.control_group_cost_truelift.orders_forgone_a_week", "int")
FORECAST_RATIO = v("ev.main.forecast.truelift_design_in_todays_market.ratio_forecast_to_truth", "pct0")
PRE_PAY = {k: v(f"ev.pre_discount_commission.policies.{k}.offers_that_pay") for k in ("today_blanket", "truelift")}


def market(k: str) -> str:
    return lakh(x(f"{P}.{k}.restaurant_profit_change"), True)


def commission(k: str) -> str:
    return lakh(x(f"{P}.{k}.zomato_commission_change"), True)


def discount(k: str) -> str:
    return lakh(x(f"{P}.{k}.customer_savings"))


# ------------------------------------------------------------------ charts (inline SVG)
def hbars(rows: list[tuple[str, float, bool]], label: Callable[[float], str], width: int = 620, row_h: int = 50) -> str:
    """Horizontal bars, TrueLift in blue and the others in grey (data colours, never brand red)."""
    label_w, room = 200, 150
    vmax = max(abs(r[1]) for r in rows) or 1.0
    h = row_h * len(rows)
    out = [f'<svg viewBox="0 0 {width} {h}" width="{width}" height="{h}" role="img">']
    for i, (name, val, hi) in enumerate(rows):
        y = i * row_h
        w = max(3.0, (width - label_w - room) * abs(val) / vmax)
        weight = 700 if hi else 500
        out.append(f'<text x="0" y="{y + row_h / 2 + 6:.0f}" font-size="18" fill="{INK}">{esc(name)}</text>')
        out.append(
            f'<rect x="{label_w}" y="{y + 11}" width="{w:.1f}" height="{row_h - 22}" rx="5" '
            f'fill="{BLUE if hi else GREY}"/>'
        )
        out.append(
            f'<text x="{label_w + w + 10:.1f}" y="{y + row_h / 2 + 6:.0f}" font-size="18" font-weight="{weight}" '
            f'fill="{INK}">{esc(label(val))}</text>'
        )
    out.append("</svg>")
    return "".join(out)


def decline_chart(width: int = 640, height: int = 330) -> str:
    """Zomato's commission when owners decline blanket offers blind, against TrueLift's."""
    ca = EV["main"]["consent_attrition"]
    pts = [(0.0, EV["main"]["policies"]["today_blanket"]["zomato_commission_change"])]
    pts += sorted(
        (float(k.rstrip("%")) / 100, d["zomato_commission_change"])
        for k, d in ca["blanket_owners_decline_blind"].items()
    )
    tl = ca["truelift_all_approve"]["zomato_commission_change"]
    left, right, top, bottom = 64, 180, 16, 54
    lo = math.floor(min(p[1] for p in pts + [(0, tl)]) / 1e5)
    hi = math.ceil(max(p[1] for p in pts + [(0, tl)]) / 1e5 * 2) / 2
    xmax = max(p[0] for p in pts)

    def sx(s: float) -> float:
        return left + (width - left - right) * s / xmax

    def sy(val: float) -> float:
        return top + (height - top - bottom) * (1 - (val / 1e5 - lo) / (hi - lo))

    out = [f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img">']
    tick = lo
    while tick <= hi + 1e-9:
        y = sy(tick * 1e5)
        out.append(f'<line x1="{left}" x2="{width - right}" y1="{y:.1f}" y2="{y:.1f}" stroke="{LINE}"/>')
        out.append(
            f'<text x="{left - 10}" y="{y + 5:.1f}" font-size="14" fill="{MUTED}" text-anchor="end">₹{tick:g}L</text>'
        )
        tick += 0.5
    for s, _ in pts:
        out.append(
            f'<text x="{sx(s):.1f}" y="{height - bottom + 24}" font-size="14" fill="{MUTED}" '
            f'text-anchor="middle">{half_up(100 * s)}%</text>'
        )
    out.append(
        f'<text x="{(left + width - right) / 2:.0f}" y="{height - 6}" font-size="14" fill="{MUTED}" '
        f'text-anchor="middle">Owners who stop approving blanket offers blind</text>'
    )
    y_tl = sy(tl)
    out.append(
        f'<line x1="{left}" x2="{width - right}" y1="{y_tl:.1f}" y2="{y_tl:.1f}" stroke="{BLUE}" stroke-width="3"/>'
    )
    out.append(
        f'<text x="{width - right + 10}" y="{y_tl + 5:.1f}" font-size="15" font-weight="700" fill="{BLUE}">'
        f"TrueLift {esc(lakh(tl, True))}</text>"
    )
    path = " ".join(f"{'M' if i == 0 else 'L'}{sx(s):.1f},{sy(val):.1f}" for i, (s, val) in enumerate(pts))
    out.append(f'<path d="{path}" fill="none" stroke="{GREY_DARK}" stroke-width="3"/>')
    for s, val in pts:
        out.append(f'<circle cx="{sx(s):.1f}" cy="{sy(val):.1f}" r="5" fill="{GREY_DARK}"/>')
    s_last, v_last = pts[-1]
    out.append(
        f'<text x="{width - right + 10}" y="{sy(v_last) + 5:.1f}" font-size="15" fill="{INK2}">'
        f"Blanket {esc(lakh(v_last, True))}</text>"
    )
    out.append("</svg>")
    return "".join(out)


def coverage_chart(width: int = 470, height: int = 300) -> str:
    """How often the truth fell inside the weekly 80% range, after one, two and four weeks."""
    m = EV["main"]["measurement"]
    rows = [(w, m[f"after_{w}_weeks"]["coverage_80"]) for w in (1, 2, 4)]
    left, bottom, top = 40, 46, 30
    band = (width - left) / len(rows)

    def sy(share: float) -> float:
        return top + (height - top - bottom) * (1 - share)

    out = [f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img">']
    for i, (w, share) in enumerate(rows):
        bx = left + i * band + band * 0.22
        bw = band * 0.56
        out.append(
            f'<rect x="{bx:.1f}" y="{sy(share):.1f}" width="{bw:.1f}" height="{sy(0) - sy(share):.1f}" rx="5" fill="{BLUE}"/>'
        )
        out.append(
            f'<text x="{bx + bw / 2:.1f}" y="{sy(share) - 10:.1f}" font-size="20" font-weight="700" fill="{INK}" '
            f'text-anchor="middle">{fmt(share, "pct0")}</text>'
        )
        out.append(
            f'<text x="{bx + bw / 2:.1f}" y="{height - 16}" font-size="15" fill="{MUTED}" text-anchor="middle">'
            f"after {w} week{'s' if w > 1 else ''}</text>"
        )
    y80 = sy(0.8)
    out.append(
        f'<line x1="{left - 6}" x2="{width}" y1="{y80:.1f}" y2="{y80:.1f}" stroke="{INK2}" stroke-dasharray="6 5"/>'
    )
    out.append(f'<text x="{left - 10}" y="{y80 + 5:.1f}" font-size="13" fill="{INK2}" text-anchor="end">80%</text>')
    out.append(f'<line x1="{left - 6}" x2="{width}" y1="{sy(0):.1f}" y2="{sy(0):.1f}" stroke="{LINE}"/>')
    out.append("</svg>")
    return "".join(out)


def grid100(anyway: float) -> str:
    """One hundred orders that used a blanket offer: grey would have come anyway, blue are extra."""
    n_anyway = half_up(100 * anyway)
    size, gap = 30, 6
    out = [f'<svg viewBox="0 0 {10 * (size + gap)} {10 * (size + gap)}" width="{10 * (size + gap)}" role="img">']
    for k in range(100):
        r, c = divmod(k, 10)
        fill = GREY if k < n_anyway else BLUE
        out.append(
            f'<rect x="{c * (size + gap)}" y="{r * (size + gap)}" width="{size}" height="{size}" rx="5" fill="{fill}"/>'
        )
    out.append("</svg>")
    return "".join(out)


def md_table(md: str, cls: str = "data") -> str:
    """A generated Markdown table (scripts/render_tables.py) as HTML, so slides and documents match."""
    lines = [ln.strip() for ln in md.strip().splitlines() if ln.strip().startswith("|")]
    head = [c.strip() for c in lines[0].strip("|").split("|")]
    out = [f'<table class="{cls}"><thead><tr>' + "".join(f"<th>{esc(c)}</th>" for c in head) + "</tr></thead><tbody>"]
    for ln in lines[2:]:
        cells = [c.strip().replace("**", "") for c in ln.strip("|").split("|")]
        out.append("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in cells) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def qr_svg(url: str) -> str:
    import qrcode
    import qrcode.image.svg

    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, border=1)
    svg = img.to_string(encoding="unicode")
    svg = svg[svg.index("<svg") :]
    return svg.replace("<svg ", '<svg class="qr" role="img" aria-label="QR code for the demo" ', 1)


def qr_png(url: str) -> bytes:
    import qrcode

    buf = io.BytesIO()
    qrcode.make(url, border=1, box_size=12).save(buf, format="PNG")
    return buf.getvalue()


# ------------------------------------------------------------------ the slides
@dataclass
class Slide:
    title: str
    body: str  # HTML
    points: list[str]  # the same content as plain sentences, for the editable PPTX
    notes: list[str]
    source: str = ""
    visual: bool = True  # screenshot the visual for the PPTX
    registers: dict[str, str] = field(default_factory=dict)  # leader / domain expert / engineer
    cut: bool = False  # part of the five-minute cut
    appendix: bool = False
    seconds: int = 0


SIM = "Customers, orders and profits are simulated on 300 real 2019 Bengaluru listings."


def money_table() -> str:
    rows = (
        ("Food sales", rs(FULL.basket), rs(DISC.basket)),
        ("Discount", "–", f"−{rs(DISC.discount)}"),
        ("Commission (25% of the bill)", f"−{rs(FULL.commission)}", f"−{rs(DISC.commission)}"),
        ("GST on commission (18%)", f"−{rs(FULL.gst_on_commission)}", f"−{rs(DISC.gst_on_commission)}"),
        ("Food and packaging (37%)", f"−{rs(FULL.food_cost)}", f"−{rs(DISC.food_cost)}"),
    )
    body = "".join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>" for a, b, c in rows)
    return (
        '<table class="money"><thead><tr><th>One order</th><th>Full price</th>'
        f"<th>{rs(DISC.discount)} off</th></tr></thead><tbody>{body}"
        f'<tr class="total"><td>Restaurant keeps</td><td>{rs(FULL.restaurant_profit)}</td>'
        f"<td>{rs(DISC.restaurant_profit)}</td></tr></tbody></table>"
    )


def slides() -> list[Slide]:
    anyway_n = half_up(100 * BL_ANYWAY)
    loss = rs(FULL.restaurant_profit - DISC.restaurant_profit)
    lat = NS["lat"]
    s: list[Slide] = []

    s.append(
        Slide(
            title="TrueLift",
            body=(
                '<div class="title-wrap"><div><p class="tag">Restaurant discounts on Zomato are judged by the orders '
                "that use them. TrueLift judges them by the orders they create, inside the owner's OTP approval.</p>"
                '<p class="team">Team Banana, IIT Gandhinagar<br>Yash Goyal · Bhavay Goyal · Kshitish Madbhavi</p>'
                '<p class="event">IITGN × Eternal hackathon, Round 2</p></div>'
                f'<div class="qr-card" data-shot="visual-01">{qr_svg(DEMO_URL)}<span class="cta">Try the demo on your phone</span>'
                f'<span class="url">{esc(DEMO_URL.removeprefix("https://"))}</span></div></div>'
            ),
            points=[
                "Restaurant discounts on Zomato are judged by the orders that use them. TrueLift judges them by the "
                "orders they create, inside the owner's OTP approval.",
                "Team Banana, IIT Gandhinagar: Yash Goyal, Bhavay Goyal, Kshitish Madbhavi.",
                f"Demo: {DEMO_URL}",
            ],
            notes=[
                "Say the line and stop. Then point at the code: anyone can open the demo on a phone now; it needs no "
                "login and nothing on it can break.",
            ],
            cut=True,
            seconds=20,
        )
    )
    s.append(
        Slide(
            title="Since August 2026, every restaurant-funded offer needs the owner's OTP",
            body=(
                '<div class="col"><ol class="timeline">'
                "<li><b>July–August 2026.</b> Restaurant owners in Bengaluru object to discounts deducted without clear "
                "consent. They ask for approval for a fixed period, fresh approval to extend it, and itemised payouts.</li>"
                "<li><b>8 August 2026.</b> Zomato agrees: restaurant-funded campaigns are opt-in and start only after the "
                "owner approves them by OTP.</li>"
                "<li><b>Now.</b> An owner who cannot see whether an offer pays has every reason to stop approving it.</li>"
                "</ol></div>"
                '<div class="col side"><div class="card"><p class="k">Eternal\'s advertising and promotion spend</p>'
                '<p class="big">₹1,138 Cr</p><p class="small">in Q2 FY27, up 41% from ₹806 Cr a year earlier. Discounting '
                "is rising again, so knowing what it buys is worth more.</p></div></div>"
            ),
            points=[
                "July–August 2026: restaurant owners in Bengaluru object to discounts deducted without clear consent, "
                "and ask for approval for a fixed period, fresh approval to extend it, and itemised payouts.",
                "8 August 2026: Zomato agrees that restaurant-funded campaigns are opt-in and start only after the "
                "owner approves them by OTP.",
                "Now: an owner who cannot see whether an offer pays has every reason to stop approving it.",
                "Eternal's advertising and promotion spend: ₹1,138 Cr in Q2 FY27, up 41% from ₹806 Cr a year earlier.",
            ],
            notes=[
                "The OTP turns every discount into a decision the owner signs. Today the owner signs blind: the report "
                "afterwards counts orders that used the offer, not orders it created.",
            ],
            source="Sources: Angel One (8 Aug 2026), The Week (Jul–Aug 2026), Eternal Q2 FY27 results",
            visual=False,
            seconds=35,
        )
    )
    s.append(
        Slide(
            title=f"₹60 off a ₹400 order pays only if {BREAK_EVEN} of every 100 orders using it are extra",
            body=(
                f'<div class="col" data-shot="visual-03">{money_table()}</div>'
                '<div class="col side">'
                f"<p>Each order that would have come anyway now earns <b>{loss} less</b>. Each extra order earns "
                f"<b>{rs(DISC.restaurant_profit)}</b>.</p>"
                f"<p>So the offer breaks even when <b>{BREAK_EVEN} in 100</b> of its orders are extra; <b>{BREAK_EVEN_PRE} "
                "in 100</b> if commission is charged on the bill before the discount.</p>"
                '<p class="small">Computed by <code>truelift/economics.py</code>, the code the service uses.</p></div>'
            ),
            points=[
                f"At full price the restaurant keeps {rs(FULL.restaurant_profit)} of a ₹400 order; with ₹60 off it keeps "
                f"{rs(DISC.restaurant_profit)}.",
                f"Each order that would have come anyway earns {loss} less; each extra order earns "
                f"{rs(DISC.restaurant_profit)}.",
                f"The offer breaks even when {BREAK_EVEN} in 100 of its orders are extra ({BREAK_EVEN_PRE} in 100 if "
                "commission is charged before the discount).",
            ],
            notes=[
                "One order, exact. Commission is 25% of the bill plus 18% GST on it, food and packaging 37%. "
                f"The break-even is {BREAK_EVEN}%: below that share of extra orders, the discount loses money.",
                "Whether commission is charged before or after the discount is a question for Eternal; we ran both.",
            ],
            source="Source: truelift/economics.py (commission 25% + 18% GST, food and packaging 37%)",
            cut=True,
            seconds=45,
        )
    )
    s.append(
        Slide(
            title="The report counts every order that used the offer. It cannot say which ones the offer created",
            body=(
                f'<div class="col grid" data-shot="visual-04">{grid100(BL_ANYWAY)}</div>'
                '<div class="col side">'
                f'<p class="legend"><i class="sw grey"></i><b>{anyway_n}</b> of every 100 orders using a blanket offer would '
                "have come anyway</p>"
                f'<p class="legend"><i class="sw blue"></i><b>{100 - anyway_n}</b> are extra</p>'
                f"<p>With TrueLift's versions, {TL_ANYWAY} would have come anyway.</p>"
                "<p>Only customers who did not see the offer can show what would have happened without it. "
                "No report can, so owners approve blind.</p></div>"
            ),
            points=[
                f"Of every 100 orders using a blanket offer, {anyway_n} would have come anyway; {100 - anyway_n} are extra.",
                f"With TrueLift's versions, {TL_ANYWAY} would have come anyway.",
                "Only customers who did not see the offer can show what would have happened without it.",
            ],
            notes=[
                "This is the core of the problem. The report shows 100 orders and every one looks like a success. "
                f"In our simulated market {anyway_n} of them would have happened anyway.",
            ],
            source=f"Source: reports/evaluation.json. {SIM}",
            seconds=35,
        )
    )
    hooks = (
        (
            "1",
            "Quote",
            "Before the OTP",
            "A forecast of extra orders and profit with a range, and a better version of the same discount, or no offer.",
        ),
        (
            "2",
            "Serve",
            "Customer opens a menu",
            "A table lookup decides who sees the discount; 1 in 10 eligible customers is held out.",
        ),
        (
            "3",
            "Payout",
            "Every week",
            "The restaurant pays for its own offer, itemised. Zomato co-funds only what it measures.",
        ),
        (
            "4",
            "Measure",
            "Every week",
            "Held-out customers against the rest: extra profit with a range, on WhatsApp. Renewal needs a new OTP.",
        ),
    )
    s.append(
        Slide(
            title="TrueLift adds four calls to the offer flow Zomato already has",
            body=(
                '<div class="col"><div class="hooks" data-shot="visual-05">'
                + "".join(
                    f'<div class="hook"><span class="n">{n}</span><h3>{t}</h3><p class="when">{w}</p><p>{d}</p></div>'
                    for n, t, w, d in hooks
                )
                + '</div><p class="under">No new screens: the forecast sits on the OTP screen, the result arrives on '
                "WhatsApp, and nothing changes in how customers order.</p></div>"
            ),
            points=[f"{n}. {t} ({w.lower()}): {d}" for n, t, w, d in hooks]
            + ["No new screens: the forecast sits on the OTP screen and the result arrives on WhatsApp."],
            notes=[
                "Four hooks. The quote is the only one the owner sees before signing; serving is a lookup, no model on "
                "the customer's path; the held-out customers are what make the weekly number true.",
            ],
            source="docs/architecture.md, docs/integration_blueprint.md",
            seconds=40,
        )
    )
    steps = (
        "Tap <b>Create an offer</b>. Your usual ₹60 off is already set.",
        "Read the forecast, then tap <b>Use this version</b>.",
        "<b>Continue to approve</b> and enter the OTP shown on screen.",
        "Tap <b>Simulate the first week</b>, then each next week.",
        "Tap <b>Send to my WhatsApp</b>: the owner's weekly message.",
    )
    s.append(
        Slide(
            title="Try it: you own a restaurant. Create an offer",
            body=(
                '<div class="col"><ol class="steps">' + "".join(f"<li>{t}</li>" for t in steps) + "</ol>"
                '<p class="small">Every answer on the public demo was computed by the service and saved, so nothing you '
                "tap can break it. The guided demo tells the same story in ten steps.</p></div>"
                f'<div class="col side center"><div class="qr-card big" data-shot="visual-06">{qr_svg(DEMO_URL)}'
                f'<span class="url">{esc(DEMO_URL.removeprefix("https://"))}</span></div></div>'
            ),
            points=[
                "Tap Create an offer: your usual ₹60 off is already set.",
                "Read the forecast, then tap Use this version.",
                "Continue to approve and enter the OTP shown on screen.",
                "Tap Simulate the first week, then each next week.",
                "Tap Send to my WhatsApp: the owner's weekly message.",
                f"Demo: {DEMO_URL}",
            ],
            notes=[
                "Live, three minutes. One person drives the laptop, the other speaks. Primary: the offline bundle on "
                "the laptop's own server; fallback: the recording. Follow the runbook in docs/pitch/runbook.md.",
                "Say what happened, not only what was forecast: the report shows many orders, the control group says "
                "how many were extra.",
            ],
            source="Live demo; offline copy in dist/truelift-offline/",
            cut=True,
            seconds=180,
        )
    )
    rows_market = [(name, x(f"{P}.{k}.restaurant_profit_change"), k == "truelift") for k, name in COLS]
    rows_disc = [(name, x(f"{P}.{k}.customer_savings"), k == "truelift") for k, name in COLS]
    s.append(
        Slide(
            title=f"For restaurants: {TL_PAY} of {TL_N} TrueLift offers pay, against {BL_PAY} of {N_REST} blanket offers",
            body=(
                '<div class="col" data-shot="visual-07">'
                '<p class="k">Restaurant profit against no offers at all, a week</p>'
                + hbars(rows_market, lambda val: lakh(val, True))
                + '<p class="k gap">Discount given, a week</p>'
                + hbars(rows_disc, lambda val: lakh(val))
                + "</div>"
                '<div class="col side">'
                f"<p>Restaurants make <b>{market('truelift')}</b> against {market('today_blanket')} with blanket offers, "
                f"while giving <b>{LESS_DISCOUNT} less discount</b>.</p>"
                f"<p>Against the simple rule (new customers only, {RULE_PAY} of {N_REST} offers pay), TrueLift still "
                "makes more.</p>"
                f"<p>At {NO_OFFER} restaurants no version pays, and TrueLift says so: no offer.</p></div>"
            ),
            points=[
                f"{TL_PAY} of {TL_N} TrueLift offers pay, against {BL_PAY} of {N_REST} blanket offers and {RULE_PAY} of "
                f"{N_REST} for the new-customers rule.",
                f"Restaurant profit against no offers: {market('truelift')} a week with TrueLift, "
                f"{market('today_blanket')} with blanket offers, {market('rule_new_customers')} with the rule.",
                f"Discount given: {discount('truelift')} with TrueLift against {discount('today_blanket')} for blanket offers.",
                f"At {NO_OFFER} restaurants no version pays, and TrueLift advises no offer.",
            ],
            notes=[
                "Lead with offers that pay: that is what an owner feels. Then the market-wide profit, which counts "
                "the orders restaurants take from each other.",
            ],
            registers={
                "Leader": f"Restaurants make {market('truelift')} a week with {LESS_DISCOUNT} less discount.",
                "Domain expert": "Owners keep their discount size; TrueLift changes who sees it, the minimum order, "
                "the time and the Brand Pack reward.",
                "Engineer": "Each suggestion is the best of 34 versions, calibrated on the shadow phase's random "
                "holdouts and shown only with at least a 60% chance of making money.",
            },
            source=f"Source: reports/evaluation.json; {SEEDS} market seeds agree (README). {SIM}",
            cut=True,
            seconds=45,
        )
    )
    s.append(
        Slide(
            title="For Zomato: commission is higher too, and the gap widens when owners stop approving blind",
            body=(
                f'<div class="col" data-shot="visual-08"><p class="k">Zomato commission against no offers, a week</p>{decline_chart()}</div>'
                '<div class="col side">'
                f"<p>With every owner approving, Zomato's commission is <b>{commission('truelift')}</b> with TrueLift "
                f"against {commission('today_blanket')} with blanket offers, in every one of {SEEDS} market seeds.</p>"
                f"<p>An owner who can see which offers pay keeps approving them; an owner who cannot may stop approving any.</p>"
                f"<p>{PLATFORM_SHARE} of TrueLift's extra orders are new to Zomato, not taken from another "
                "restaurant.</p></div>"
            ),
            points=[
                f"Zomato commission against no offers: {commission('truelift')} a week with TrueLift against "
                f"{commission('today_blanket')} with blanket offers, in every one of {SEEDS} market seeds.",
                "If owners stop approving blanket offers blind, blanket commission falls further below TrueLift's.",
                f"{PLATFORM_SHARE} of TrueLift's extra orders are new to Zomato.",
            ],
            notes=[
                "Zomato earns commission on orders, and TrueLift has slightly fewer orders than blanket offers. It "
                "still earns more, because order values are higher and less of each bill is discount.",
                "The chart is the risk case: owners who cannot see whether offers pay start declining them.",
            ],
            registers={
                "Leader": "Commission does not fall when discounts shrink, and it holds up if owners start declining.",
                "Domain expert": "An owner who sees that an offer pays keeps approving it; that is the commission "
                "Zomato keeps.",
                "Engineer": f"The commission result has the same sign in all {SEEDS} seeds; the attrition scenarios "
                "are in reports/evaluation.json under consent_attrition.",
            },
            source=f"Source: reports/evaluation.json (policies, consent_attrition, seeds). {SIM}",
            cut=True,
            seconds=45,
        )
    )
    s.append(
        Slide(
            title="The simulator knows the truth, so every estimate is checked against it",
            body=(
                '<div class="col" data-shot="visual-09"><p class="k">Weekly result: truth inside the 80% range</p>'
                f"{coverage_chart()}</div>"
                '<div class="col side"><ul class="facts">'
                f'<li>"Keep" verdicts truly positive: <b>{KEEP[1][0]} of {KEEP[1][1]}</b> after one week, '
                f"<b>{KEEP[4][0]} of {KEEP[4][1]}</b> after four.</li>"
                f"<li>Placebo offers that change nothing: paused <b>{AA}</b> over four weekly looks "
                f"(the old rule: {AA_BEFORE}).</li>"
                "<li>Real randomised data (ads and e-mail, not food): uplift models beat the shortcut in all "
                f"{HILL_SPLITS} splits of Hillstrom's women's e-mail; on Criteo's purchases the shortcut wins "
                f"({CRITEO[(1, 'response')]} against {CRITEO[(1, 't_learner')]}). We report both.</li>"
                "</ul></div>"
            ),
            points=[
                f"Truth inside the weekly 80% range: {COVERAGE[1]} after one week, {COVERAGE[2]} after two, "
                f"{COVERAGE[4]} after four.",
                f"'Keep' verdicts truly positive: {KEEP[1][0]} of {KEEP[1][1]} after one week, {KEEP[4][0]} of "
                f"{KEEP[4][1]} after four.",
                f"Placebo offers that change nothing: paused {AA} over four weekly looks.",
                f"Real data: uplift models win on Hillstrom's women's e-mail in all {HILL_SPLITS} splits; on Criteo's "
                f"purchases the 'likely to buy anyway' ranking wins ({CRITEO[(1, 'response')]} against "
                f"{CRITEO[(1, 't_learner')]}).",
            ],
            notes=[
                "Ranges are built to miss about one time in five: after one week they do, and later they miss less often. A pause needs the offer's own control "
                "group to show a loss, so placebo offers are almost never paused.",
                "Say the real-data result honestly: on one dataset the simple shortcut wins.",
            ],
            registers={
                "Leader": f"When TrueLift says keep, it is right {KEEP[4][0]} times in {KEEP[4][1]} after four weeks.",
                "Domain expert": "The owner sees a range that narrows every week as the restaurant's own evidence grows.",
                "Engineer": "Combined estimate: the offer's control group plus the model, weighted by noise that is "
                "re-estimated every week across running offers; the pause uses an always-valid boundary.",
            },
            source="Sources: reports/evaluation.json, reports/uplift_validation_*.json. " + SIM,
            seconds=45,
        )
    )
    s.append(
        Slide(
            title="We audited our own work: 50 findings, all fixed. Two limits remain",
            body=(
                '<div class="col"><p class="k">Three of the fixes</p><ul class="facts">'
                "<li><b>Serving and measurement held out different customers.</b> Now one hashed assignment, "
                "used and tested everywhere.</li>"
                "<li><b>The simulator paid Zomato's co-funding on every redemption.</b> Now only for customers new "
                "to Zomato, exactly as the engine does.</li>"
                "<li><b>Placebo offers were paused on noise.</b> A pause now needs the offer's own always-valid "
                "evidence.</li></ul></div>"
                '<div class="col side"><p class="k">What is still not right</p><ul class="facts">'
                f"<li>A suggested version's stated advantage is about <b>{INFLATION} times</b> its true one, though "
                f"{TRULY_BETTER} truly beat the owner's.</li>"
                f"<li>The four-week estimate over-states the truth by <b>{DRAWS_BIAS}</b> an offer on average, "
                "inherited from the model.</li></ul></div>"
            ),
            points=[
                "Serving and measurement held out different customers: now one hashed assignment, tested.",
                "The simulator paid Zomato's co-funding on every redemption: now only for customers new to Zomato.",
                "Placebo offers were paused on noise: a pause now needs the offer's own always-valid evidence.",
                f"Still not right: a suggested version's stated advantage is about {INFLATION} times its true one "
                f"({TRULY_BETTER} truly beat the owner's).",
                f"Still not right: the four-week estimate over-states the truth by {DRAWS_BIAS} an offer on average.",
            ],
            notes=[
                "Judges trust a team that shows its own mistakes. Each fix has its guard in docs/what_we_tested.md; "
                "the corrections with before and after are in DEVLOG.md.",
            ],
            source="docs/what_we_tested.md, CHANGELOG.md, DEVLOG.md (corrections)",
            visual=False,
            seconds=35,
        )
    )
    phases = (
        (
            "1",
            "Shadow holdout",
            "2% of eligible customers held out of offers owners already run, in one city. Nothing shown to owners.",
        ),
        (
            "2",
            "Measure",
            f"Forecast and weekly result for a random half of the pilot restaurants: {PILOT_ARM} in each "
            f"half, {PILOT_TOTAL} in all.",
        ),
        ("3", "Target", "Owners in that half may let TrueLift choose who sees the offer."),
        ("4", "Scale", "City by city, with the same guardrails."),
    )
    s.append(
        Slide(
            title="From prototype to pilot: measure first, change who sees offers later",
            body=(
                '<div class="col"><div class="hooks phases" data-shot="visual-11">'
                + "".join(
                    f'<div class="hook"><span class="n">{n}</span><h3>{t}</h3><p>{d}</p></div>' for n, t, d in phases
                )
                + '</div><p class="under">Each phase starts only when the one before has passed its checks (sample-ratio '
                "checks, placebo offers, renewal rate) and stops at once if a guardrail is breached. The shadow kit "
                "already measures offers from logs in Zomato's event format.</p></div>"
            ),
            points=[f"{n}. {t}: {d}" for n, t, d in phases],
            notes=[
                "The pilot is sized to detect a rise in renewals from 60% to 70% with 80% power; the 60% is a "
                "placeholder Eternal would replace with its own figure.",
            ],
            source="docs/integration_blueprint.md, reports/pilot_sample_size.json",
            seconds=35,
        )
    )
    s.append(
        Slide(
            title="What we would like from Eternal",
            body=(
                '<div class="col"><ol class="steps ask">'
                f"<li>Is commission charged on the bill before or after the discount? (Break-even {BREAK_EVEN}% against "
                f"{BREAK_EVEN_PRE}% at ₹60 off a ₹400 order.)</li>"
                "<li>Could we run the shadow kit on anonymised offer logs for one city?</li>"
                "<li>What does the OTP approval screen show today, and how often do owners decline?</li></ol>"
                '<p class="team">Team Banana: Yash Goyal · Bhavay Goyal · Kshitish Madbhavi</p></div>'
                f'<div class="col side center"><div class="qr-card" data-shot="visual-12">{qr_svg(DEMO_URL)}'
                f'<span class="url">{esc(DEMO_URL.removeprefix("https://"))}</span></div></div>'
            ),
            points=[
                f"Is commission charged on the bill before or after the discount? (Break-even {BREAK_EVEN}% against "
                f"{BREAK_EVEN_PRE}%.)",
                "Could we run the shadow kit on anonymised offer logs for one city?",
                "What does the OTP approval screen show today, and how often do owners decline?",
                "Team Banana: Yash Goyal, Bhavay Goyal, Kshitish Madbhavi.",
            ],
            notes=["End on the ask, then stop talking. Leave this slide up during questions."],
            cut=True,
            seconds=25,
        )
    )

    # ---------------------------------------------------------------- appendix
    s.append(
        Slide(
            title="Appendix: how the pieces fit",
            body=(
                '<div class="col"><div class="flow" data-shot="visual-a1">'
                '<div class="lane"><h3>Partner app</h3><p>Owner creates an offer → <b>quote</b> → OTP → consent record '
                "(hash-chained, stores the forecast shown)</p></div>"
                '<div class="lane"><h3>Customer app</h3><p>Menu opens → <b>serve</b>: decision-table lookup and the '
                "(customer, offer) hash → exposure log</p></div>"
                '<div class="lane"><h3>Every week</h3><p>Exposure log + orders → <b>measure</b> → WhatsApp result, '
                "payout lines, renewal on evidence</p></div>"
                '<div class="lane"><h3>Learning</h3><p>Every held-out and shown visit is randomised training data; a '
                "candidate model is promoted only if it ranks recent held-out weeks better</p></div></div></div>"
            ),
            points=[
                "Partner app: offer → quote → OTP → consent record (hash-chained).",
                "Customer app: menu opens → serve (lookup and hash) → exposure log.",
                "Every week: exposure log and orders → measurement → WhatsApp result, payout lines, renewal.",
                "Learning: a candidate model is promoted only if it ranks recent held-out weeks better.",
            ],
            notes=[
                "For engineers: one hash decides the control group for serving and for measurement, so they cannot disagree."
            ],
            source="docs/architecture.md",
            appendix=True,
        )
    )
    lat_rows = (
        (
            "Serve one customer, over HTTP",
            f"{lat.serve_sequential.p50_ms:.1f} ms",
            f"{lat.serve_sequential.p95_ms:.1f} ms",
            f"{lat.serve_sequential.p99_ms:.1f} ms",
        ),
        (
            "Serve, inside the service",
            f"{lat.serve_sequential.server_side.p50_ms:.2f} ms",
            f"{lat.serve_sequential.server_side.p95_ms:.2f} ms",
            f"{lat.serve_sequential.server_side.p99_ms:.2f} ms",
        ),
        (
            "Serve, eight callers at once",
            f"{lat.serve_8_threads.p50_ms:.1f} ms",
            f"{lat.serve_8_threads.p95_ms:.1f} ms",
            f"{lat.serve_8_threads.p99_ms:.1f} ms",
        ),
        (
            "Quote: forecast and 34 versions",
            f"{lat.quote_sequential.p50_ms:.0f} ms",
            f"{lat.quote_sequential.p95_ms:.0f} ms",
            f"{lat.quote_sequential.p99_ms:.0f} ms",
        ),
    )
    s.append(
        Slide(
            title="Appendix: speed on a laptop, measured over HTTP",
            body=(
                '<div class="col" data-shot="visual-a2"><table class="data"><thead><tr><th></th><th>Median</th><th>95th '
                "percentile</th><th>99th percentile</th></tr></thead><tbody>"
                + "".join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td><td>{d}</td></tr>" for a, b, c, d in lat_rows)
                + "</tbody></table>"
                f'<p class="small">Eight callers at once: {v("lat.serve_8_threads.throughput_per_second", "int")} '
                f"menu decisions a second. Measured by <code>scripts/bench_latency.py</code> on "
                f"{lat.hardware.logical_cpus} logical CPUs. The quote is shown to an owner, not on a customer's path; "
                "inside Zomato it would be computed in batch.</p></div>"
            ),
            points=[f"{a}: median {b}, 95th percentile {c}, 99th percentile {d}." for a, b, c, d in lat_rows],
            notes=["Serving is a dictionary lookup and a hash; no model runs while a customer waits."],
            source="Source: reports/latency.json",
            appendix=True,
        )
    )
    s.append(
        Slide(
            title="Appendix: the weekly estimate, checked against the truth",
            body=(
                f'<div class="col" data-shot="visual-a3">{md_table(measurement_table(EV))}'
                '<p class="small">The offer\'s own control group alone is unbiased but noisy; the model alone is '
                "steady but can be wrong; TrueLift combines them by how noisy each is, re-estimated every week across "
                "running offers. A pause needs the offer's own control group (at least 30 held-out customers) to "
                "cross an always-valid boundary.</p></div>"
            ),
            points=[
                f"Truth inside the 80% range: {COVERAGE[1]}, {COVERAGE[2]}, {COVERAGE[4]} after one, two, four weeks.",
                "The combined estimate's average error is below both the control group alone and the model alone.",
                "A pause needs the offer's own control group to cross an always-valid boundary.",
            ],
            notes=[
                f"Known bias: over ten holdout draws the four-week estimate over-states the truth by {DRAWS_BIAS} an offer."
            ],
            source=f"Source: reports/evaluation.json (measurement). {SIM}",
            appendix=True,
        )
    )
    bounds = NS["sens"].boundaries
    s.append(
        Slide(
            title="Appendix: five market seeds, eight assumptions, and where the claims stop holding",
            body=(
                f'<div class="col" data-shot="visual-a4">{md_table(seeds_table(EV))}</div>'
                '<div class="col side"><p class="k">Where a claim stops holding (sensitivity sweep)</p><ul class="facts small">'
                + "".join(f"<li>{esc(b.split(' (')[0])}</li>" for b in bounds[:5])
                + "</ul></div>"
            ),
            points=["Mean and spread over five market seeds are in the table."]
            + [b.split(" (")[0] + "." for b in bounds[:5]],
            notes=["Say the boundaries plainly; they are the honest answer to 'what if your assumptions are wrong'."],
            source=f"Sources: reports/evaluation.json (seeds), reports/sensitivity.json. {SIM}",
            appendix=True,
        )
    )
    s.append(
        Slide(
            title="Appendix: who gets discounts, and what the model never reads",
            body=(
                f'<div class="col" data-shot="visual-a5">{md_table(fairness_table(EV))}'
                '<p class="small">Inputs are order and visit history, the listing, the time and the offer; a test fails '
                "if the model reads location, device, payment method or anything standing in for income. Held-out "
                "customers pay the menu price, never more. Owners see no order counts for a group of fewer than 20 "
                "customers.</p></div>"
            ),
            points=[
                "Under targeting, regulars are offered fewer discounts because they order anyway; a Brand Pack reward "
                "for regulars closes the gap without lowering profit.",
                "The model never reads location, device, payment method or income proxies; a test enforces it.",
                "No order counts are shown for groups of fewer than 20 customers.",
            ],
            notes=["docs/privacy_and_fairness.md has the regulatory map, marked as our reading."],
            source=f"Source: reports/evaluation.json (fairness). {SIM}",
            appendix=True,
        )
    )
    s.append(
        Slide(
            title="Appendix: research with restaurant owners",
            body=(
                '<div class="col"><p><b>Not yet conducted.</b> The kit is ready: question sheets in English (Hindi and '
                "Gujarati drafts), a consent script, comprehension cards that put today's offer report beside "
                "TrueLift's weekly result, and a note template.</p>"
                "<p>What we will bring back: whether commission is charged before or after the discount, what an offer "
                "report and the OTP screen show, and which wording owners read correctly.</p>"
                '<p class="small">We publish no finding we have not collected (docs/field_research.md).</p></div>'
            ),
            points=[
                "Not yet conducted. The kit is ready: question sheets, consent script, comprehension cards, note template.",
                "We will bring back: the commission base, what reports and the OTP screen show, which wording owners read.",
            ],
            notes=["If asked: say plainly that the interviews are not done yet, and what the kit will find out."],
            source="docs/field_research.md, docs/field_research/",
            visual=False,
            appendix=True,
        )
    )
    s.append(
        Slide(
            title=f"Appendix: if commission is charged before the discount, break-even rises to {BREAK_EVEN_PRE} in 100",
            body=(
                '<div class="col"><p>Charged on the full bill, ₹60 off a ₹400 order leaves the restaurant '
                f"{v('pre.per_order_discounted.restaurant_profit', 'inr')} instead of {rs(DISC.restaurant_profit)}.</p>"
                f"<p>In that market {PRE_PAY['today_blanket']} of {N_REST} blanket offers pay, against "
                f"{PRE_PAY['truelift']} TrueLift offers. The order of the policies does not change.</p>"
                '<p class="small">Third-party calculators disagree on the base; one payout statement would settle it.</p></div>'
            ),
            points=[
                f"Break-even {BREAK_EVEN} in 100 if commission is on the discounted bill, {BREAK_EVEN_PRE} in 100 if on the full bill.",
                f"With commission on the full bill: {PRE_PAY['today_blanket']} of {N_REST} blanket offers pay, "
                f"{PRE_PAY['truelift']} TrueLift offers.",
            ],
            notes=["This is the first question for Eternal and for the owner interviews."],
            source=f"Sources: truelift/economics.py, reports/evaluation.json (pre_discount_commission). {SIM}",
            visual=False,
            appendix=True,
        )
    )
    s.append(
        Slide(
            title="Appendix: what it costs to run",
            body=(
                '<div class="col"><ul class="facts">'
                f"<li><b>The control group.</b> Holding out 1 in 10 eligible customers gives up {CONTROL_COST} of "
                f"restaurant profit a week across the 300 restaurants ({CONTROL_ORDERS} orders). It is the price of "
                "knowing.</li>"
                "<li><b>Serving.</b> A lookup and a hash per menu open; decision tables are built when an offer is "
                "approved.</li>"
                "<li><b>Quotes and measurement.</b> Batch work: a quote when an owner creates an offer, a measurement "
                "once a week per offer.</li>"
                "<li><b>Model.</b> Two gradient-boosted classifiers retrained on new randomised data, promoted only if "
                "better on recent held-out weeks.</li></ul></div>"
            ),
            points=[
                f"Control group: {CONTROL_COST} of restaurant profit a week across 300 restaurants ({CONTROL_ORDERS} orders).",
                "Serving: a lookup and a hash per menu open.",
                "Quotes and measurement: batch work.",
                "Model: retrained on new randomised data, promoted only if better.",
            ],
            notes=["Capacity numbers inside Zomato would come from Eternal (integration blueprint, section 4)."],
            source=f"Source: reports/evaluation.json (zomato_ledger). {SIM}",
            visual=False,
            appendix=True,
        )
    )
    return s


# ------------------------------------------------------------------ pages
CSS = f"""
@font-face {{ font-family: "Figtree"; font-weight: 400; src: url({FONTS}/figtree-latin-400.woff2) format("woff2"); }}
@font-face {{ font-family: "Figtree"; font-weight: 500; src: url({FONTS}/figtree-latin-500.woff2) format("woff2"); }}
@font-face {{ font-family: "Figtree"; font-weight: 600; src: url({FONTS}/figtree-latin-600.woff2) format("woff2"); }}
@font-face {{ font-family: "Figtree"; font-weight: 700; src: url({FONTS}/figtree-latin-700.woff2) format("woff2"); }}
:root {{ --red: #e23744; --ink: {INK}; --ink-2: {INK2}; --muted: {MUTED}; --line: {LINE}; --bg: #f8f8f8;
  --blue: {BLUE}; --grey: {GREY}; --font: "Figtree", system-ui, "Segoe UI", Arial, sans-serif; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; background: #e9e9e9; font-family: var(--font); color: var(--ink); }}
svg text {{ font-family: var(--font); }}
.slide {{ width: 1280px; height: 720px; margin: 24px auto; background: #fff; position: relative; overflow: hidden;
  padding: 58px 72px 80px; display: flex; flex-direction: column; box-shadow: 0 8px 24px rgba(28,28,28,.12);
  break-after: page; }}
.slide h1 {{ font-size: 37px; line-height: 1.16; font-weight: 700; letter-spacing: -0.012em; margin: 0 0 30px;
  max-width: 1100px; }}
.slide .body {{ flex: 1; display: flex; gap: 52px; min-height: 0; }}
.col {{ flex: 1; min-width: 0; }}
.col.side {{ flex: 0 0 440px; }}
.col.center {{ display: flex; align-items: center; justify-content: center; }}
p, li {{ font-size: 21px; line-height: 1.45; color: var(--ink-2); margin: 0 0 16px; }}
b {{ color: var(--ink); font-weight: 700; }}
.small, .small li {{ font-size: 16px; color: var(--muted); }}
code {{ font-size: .9em; background: #f3f3f3; padding: 1px 6px; border-radius: 5px; }}
.k {{ font-size: 16px; font-weight: 600; color: var(--muted); margin: 0 0 8px; }}
.k.gap {{ margin-top: 22px; }}
.big {{ font-size: 54px; font-weight: 700; color: var(--ink); line-height: 1.05; margin: 4px 0 10px; }}
.card {{ border: 1px solid var(--line); border-radius: 14px; padding: 24px 26px; background: #fff;
  box-shadow: 0 1px 2px rgba(54,54,54,.06), 0 2px 8px rgba(28,28,28,.08); }}
.foot {{ position: absolute; left: 72px; right: 72px; bottom: 24px; display: flex; gap: 24px; align-items: baseline;
  border-top: 1px solid var(--line); padding-top: 10px; font-size: 13px; color: var(--muted); }}
.foot .src {{ flex: 1; }}
.foot .name {{ font-weight: 700; color: var(--ink); }}
.timeline {{ list-style: none; padding: 0; margin: 0; border-left: 3px solid var(--line); }}
.timeline li {{ padding: 0 0 18px 24px; position: relative; }}
.timeline li::before {{ content: ""; position: absolute; left: -9px; top: 9px; width: 15px; height: 15px;
  border-radius: 50%; background: var(--blue); }}
table.money, table.data {{ border-collapse: collapse; width: 100%; font-size: 19px; }}
table.money th, table.money td, table.data th, table.data td {{ padding: 10px 12px; border-bottom: 1px solid var(--line);
  text-align: right; }}
table.money th:first-child, table.money td:first-child, table.data th:first-child, table.data td:first-child {{ text-align: left; }}
table.money th, table.data th {{ font-size: 15px; color: var(--muted); font-weight: 600; }}
table.money tr.total td {{ font-weight: 700; color: var(--ink); border-bottom: 0; border-top: 2px solid var(--ink); }}
table.data {{ font-size: 15px; }}
table.data td {{ color: var(--ink-2); }}
table.data td:not(:first-child) {{ white-space: nowrap; }}
.grid {{ display: flex; align-items: flex-start; }}
.legend {{ display: flex; align-items: center; gap: 12px; }}
.sw {{ display: inline-block; width: 22px; height: 22px; border-radius: 5px; flex: 0 0 22px; }}
.sw.grey {{ background: var(--grey); }} .sw.blue {{ background: var(--blue); }}
.hooks {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 18px; }}
.hook {{ border: 1px solid var(--line); border-radius: 14px; padding: 22px 20px; background: #fff;
  box-shadow: 0 1px 2px rgba(54,54,54,.06), 0 2px 8px rgba(28,28,28,.08); }}
.hook .n {{ display: inline-flex; width: 34px; height: 34px; border-radius: 50%; background: var(--ink); color: #fff;
  font-weight: 700; align-items: center; justify-content: center; font-size: 17px; }}
.hook h3 {{ font-size: 24px; margin: 14px 0 2px; }}
.hook .when {{ font-size: 15px; color: var(--muted); font-weight: 600; margin-bottom: 10px; }}
.hook p {{ font-size: 17px; }}
.under {{ margin-top: 26px; font-size: 19px; }}
.steps {{ padding-left: 28px; margin: 0 0 18px; }}
.steps li {{ margin-bottom: 12px; padding-left: 6px; }}
.facts {{ padding-left: 22px; margin: 0; }}
.facts li {{ margin-bottom: 14px; font-size: 19px; }}
.facts.small li {{ font-size: 15px; margin-bottom: 8px; color: var(--ink-2); }}
.qr-card {{ display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 22px; border-radius: 16px;
  border: 1px solid var(--line); background: #fff; box-shadow: 0 8px 12px rgba(28,28,28,.08), 0 12px 32px rgba(28,28,28,.08); }}
.qr {{ width: 190px; height: 190px; }}
.qr-card.big .qr {{ width: 260px; height: 260px; }}
.cta {{ background: var(--red); color: #fff; font-weight: 700; font-size: 17px; padding: 10px 18px; border-radius: 10px; }}
.url {{ font-size: 15px; color: var(--muted); }}
.title-slide h1 {{ font-size: 88px; letter-spacing: -0.03em; margin: 40px 0 18px; }}
.title-wrap {{ display: flex; gap: 60px; align-items: center; justify-content: space-between; }}
.tag {{ font-size: 30px; line-height: 1.35; color: var(--ink); max-width: 720px; }}
.team {{ font-size: 20px; color: var(--ink-2); margin-top: 30px; }}
.event {{ font-size: 17px; color: var(--muted); }}
.flow {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }}
.lane {{ border: 1px solid var(--line); border-radius: 14px; padding: 18px 22px; }}
.lane h3 {{ margin: 0 0 6px; font-size: 20px; }}
.lane p {{ font-size: 18px; margin: 0; }}
.ask li {{ margin-bottom: 18px; }}
.appx h1 {{ font-size: 30px; }}
aside.notes {{ display: none; width: 1280px; margin: -12px auto 24px; background: #fff; border-radius: 10px;
  padding: 16px 24px; font-size: 15px; color: var(--ink-2); }}
body.shownotes aside.notes {{ display: block; }}
body.present {{ background: #000; overflow: hidden; }}
body.present .slide {{ display: none; }}
body.present .slide.current {{ display: flex; position: fixed; left: 50%; top: 50%; margin: 0;
  transform: translate(-50%, -50%) scale(var(--scale, 1)); box-shadow: none; }}
body.present aside.notes {{ display: none; }}
@page {{ size: 1280px 720px; margin: 0; }}
@media print {{ html, body {{ background: #fff; }} .slide {{ margin: 0; box-shadow: none; }} aside.notes {{ display: none !important; }} }}
"""

JS = """
const slides = [...document.querySelectorAll('.slide')];
let i = 0, present = false;
function scale() { document.body.style.setProperty('--scale', Math.min(innerWidth / 1280, innerHeight / 720)); }
function show() {
  slides.forEach((s, k) => s.classList.toggle('current', k === i));
  if (present) scale(); else slides[i].scrollIntoView({ block: 'center' });
}
addEventListener('keydown', (e) => {
  if (['ArrowRight', 'PageDown', ' '].includes(e.key)) { i = Math.min(slides.length - 1, i + 1); show(); e.preventDefault(); }
  else if (['ArrowLeft', 'PageUp'].includes(e.key)) { i = Math.max(0, i - 1); show(); e.preventDefault(); }
  else if (e.key === 'p' || e.key === 'P') { present = !present; document.body.classList.toggle('present', present); show(); }
  else if (e.key === 'n' || e.key === 'N') { document.body.classList.toggle('shownotes'); }
});
addEventListener('resize', () => present && scale());
slides[0].classList.add('current');
"""


def deck_html(ss: list[Slide]) -> str:
    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>TrueLift: Round 2 deck</title>",
        "<!-- Generated by scripts/make_deck.py from reports/. Do not edit by hand. -->",
        f"<style>{CSS}</style></head><body>",
    ]
    main_n = sum(1 for s in ss if not s.appendix)
    for k, s in enumerate(ss, 1):
        cls = "slide title-slide" if k == 1 else ("slide appx" if s.appendix else "slide")
        num = f"A{k - main_n}" if s.appendix else str(k)
        body = s.body if k == 1 else f'<div class="body">{s.body}</div>'
        foot_src = esc(s.source) if s.source else ""
        parts.append(
            f'<section class="{cls}" data-shot="slide-{k:02d}"><h1>{esc(s.title)}</h1>{body}'
            f'<footer class="foot"><span class="name">TrueLift</span><span class="src">{foot_src}</span>'
            f"<span>{num}</span></footer></section>"
        )
        notes = "".join(f"<p>{esc(n)}</p>" for n in s.notes)
        notes += "".join(f"<p><b>{esc(r)}:</b> {esc(t)}</p>" for r, t in s.registers.items())
        parts.append(f'<aside class="notes"><b>Notes, slide {num}</b>{notes}</aside>')
    parts.append(f"<script>{JS}</script></body></html>")
    return "\n".join(parts) + "\n"


def notes_md(ss: list[Slide]) -> str:
    main_n = sum(1 for s in ss if not s.appendix)
    total = sum(s.seconds for s in ss if not s.appendix)
    cut = [k for k, s in enumerate(ss, 1) if s.cut]
    out = [
        "# Speaker notes",
        "",
        "Generated by `scripts/make_deck.py` with the deck; the numbers come from `reports/`. The full talk is",
        f"about {round(total / 60)} minutes with a three-minute live demo; the five-minute cut is slides "
        + ", ".join(map(str, cut))
        + ".",
        "",
        "Say the number first, then one sentence of meaning, then stop. Customers, orders and profits are",
        "simulated; say so once at the start of the results and whenever someone asks.",
        "",
    ]
    for k, s in enumerate(ss, 1):
        num = f"A{k - main_n}" if s.appendix else str(k)
        timing = f" ({s.seconds} s)" if s.seconds else ""
        mark = " · in the five-minute cut" if s.cut else ""
        out += [f"## {num}. {s.title}{timing}{mark}", ""]
        for n in s.notes:
            out += [n, ""]
        if s.registers:
            out += [f"- **{r}:** {t}" for r, t in s.registers.items()] + [""]
    return "\n".join(out).rstrip() + "\n"


def one_page_html(ss: list[Slide]) -> str:
    css = CSS.replace("@page { size: 1280px 720px; margin: 0; }", "@page { size: A4; margin: 0; }")
    hooks = (
        "<b>Quote</b> on the OTP screen: a forecast with a range, and a better version of the same discount.",
        "<b>Serve</b> when a customer opens the menu: a lookup; 1 in 10 eligible customers is held out.",
        "<b>Payout</b>: the restaurant pays its own offer, itemised.",
        "<b>Measure</b> every week: extra profit with a range, on WhatsApp; renewal needs a new OTP.",
    )
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>TrueLift: one page</title>
<!-- Generated by scripts/make_deck.py from reports/. Do not edit by hand. -->
<style>{css}
html, body {{ background: #fff; }}
.page {{ width: 794px; height: 1123px; margin: 0 auto; padding: 34px 44px 26px; position: relative; overflow: hidden; }}
.page h1 {{ font-size: 34px; margin: 0; letter-spacing: -0.02em; }}
.page .lead {{ font-size: 16px; color: var(--ink); line-height: 1.4; margin: 6px 0 4px; }}
.page h2 {{ font-size: 16px; margin: 18px 0 7px; }}
.page p, .page li {{ font-size: 13px; line-height: 1.45; margin: 0 0 6px; }}
.nw {{ white-space: nowrap; }}
.page ul, .page ol {{ padding-left: 18px; margin: 0; }}
.nums {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 4px; }}
.num {{ border: 1px solid var(--line); border-radius: 12px; padding: 10px 13px; }}
.num .big {{ font-size: 25px; margin: 0 0 3px; }}
.num p {{ font-size: 12px; margin: 0; }}
.two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
.page table.money {{ font-size: 12px; }}
.page table.money th, .page table.money td {{ padding: 3px 7px; }}
.page table.money th {{ font-size: 11px; }}
.bottom {{ position: absolute; left: 44px; right: 44px; bottom: 24px; display: flex; gap: 18px; align-items: center;
  border-top: 1px solid var(--line); padding-top: 12px; }}
.bottom .qr {{ width: 96px; height: 96px; flex: 0 0 96px; }}
.fine {{ font-size: 11px; color: var(--muted); }}
</style></head><body><div class="page">
<h1>TrueLift</h1>
<p class="lead">Restaurant discounts on Zomato are judged by the orders that use them. TrueLift judges them by the
orders they create, inside the owner's OTP approval.</p>
<p class="fine">Team Banana, IIT Gandhinagar: Yash Goyal, Bhavay Goyal, Kshitish Madbhavi · IITGN × Eternal hackathon, Round 2</p>
<div class="two">
<div><h2>The problem</h2>
<p>Since August 2026 a restaurant-funded offer starts only after the owner's OTP. A report counts the orders that
used an offer, not the orders it created, so owners approve blind.</p>
{money_table()}
<p style="margin-top:8px">₹60 off a ₹400 order pays only if <b>{BREAK_EVEN} of every 100</b> orders using it are extra
({BREAK_EVEN_PRE} if commission is charged before the discount).</p></div>
<div><h2>What TrueLift adds</h2><ol>{"".join(f"<li>{h}</li>" for h in hooks)}</ol>
<p>Owners keep their discount size; TrueLift changes who sees it, the minimum order, the time and the Brand Pack
reward, or advises no offer.</p></div></div>
<h2>Results in a simulated market of 300 real Bengaluru listings, a week</h2>
<div class="nums">
<div class="num"><p class="big">{TL_PAY} of {TL_N}</p><p>TrueLift offers pay for themselves, against {BL_PAY} of {N_REST} blanket offers.</p></div>
<div class="num"><p class="big">{market("truelift")}</p><p>restaurant profit against no offers (<span class="nw">{market("today_blanket")}</span> with blanket offers), with <span class="nw">{LESS_DISCOUNT}</span> less discount.</p></div>
<div class="num"><p class="big">{commission("truelift")}</p><p>Zomato commission against no offers (<span class="nw">{commission("today_blanket")}</span> with blanket offers), in all {SEEDS} market seeds.</p></div>
</div>
<div class="two"><div><h2>How we know</h2><ul>
<li>The simulator knows the truth: the weekly 80% range held it {COVERAGE[1]} of the time after one week, {COVERAGE[4]} after four.</li>
<li>Placebo offers that change nothing were paused {AA} of the time over four weekly looks.</li>
<li>On real randomised data (ads, e-mail), uplift models won on Hillstrom's women's e-mail; on Criteo's purchases the simple shortcut won. We report both.</li>
<li>We audited our own work: 50 findings, all fixed; what is still not right is published.</li></ul></div>
<div><h2>What we ask Eternal</h2><ol>
<li>Is commission charged before or after the discount?</li>
<li>Could we run our shadow kit on anonymised offer logs for one city?</li>
<li>What does the OTP screen show today, and how often do owners decline?</li></ol></div></div>
<div class="bottom">{qr_svg(DEMO_URL)}<div><p><b>Try it:</b> {esc(DEMO_URL)}</p>
<p class="fine">Restaurant names and listings are real public 2019 data; every customer, order and rupee is simulated.
Code, method and evidence: github.com/YashG1836/truelift (docs/method_and_evidence.md). Not an official Zomato or
Eternal product.</p></div></div>
</div></body></html>
"""
    return page


# ------------------------------------------------------------------ PDF and PPTX
def print_pdf(src: Path, pdf: Path, width: int, height: int, shots: Path | None = None) -> None:
    script = ROOT / "tests" / "ui" / "print_pdf.js"
    cmd = ["node", str(script), str(src), str(pdf), str(width), str(height)] + ([str(shots)] if shots else [])
    subprocess.run(cmd, check=True, cwd=ROOT / "tests" / "ui")


def build_pptx(ss: list[Slide], shots: Path, out: Path) -> None:
    from PIL import Image
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt

    def rgb(h: str) -> RGBColor:
        return RGBColor.from_string(h.lstrip("#"))

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    blank = prs.slide_layouts[6]
    main_n = sum(1 for s in ss if not s.appendix)
    for k, s in enumerate(ss, 1):
        sl = prs.slides.add_slide(blank)
        tb = sl.shapes.add_textbox(Inches(0.7), Inches(0.45), Inches(11.9), Inches(1.3)).text_frame
        tb.word_wrap = True
        tb.paragraphs[0].text = s.title
        tb.paragraphs[0].font.size = Pt(44 if k == 1 else 28)
        tb.paragraphs[0].font.bold = True
        tb.paragraphs[0].font.color.rgb = rgb(INK)
        img = shots / f"visual-{k:02d}.png" if not s.appendix else shots / f"visual-a{k - main_n}.png"
        has_img = s.visual and img.exists()
        if k == 1:
            qr = shots / "qr.png"
            qr.write_bytes(qr_png(DEMO_URL))
            sl.shapes.add_picture(str(qr), Inches(10.2), Inches(2.4), width=Inches(2.4))
        body = sl.shapes.add_textbox(
            Inches(0.7), Inches(1.9), Inches(5.9 if has_img or k == 1 else 11.9), Inches(4.9)
        ).text_frame
        body.word_wrap = True
        for j, pt in enumerate(s.points):
            para = body.paragraphs[0] if j == 0 else body.add_paragraph()
            para.text = pt
            para.font.size = Pt(17)
            para.font.color.rgb = rgb(INK2)
            para.space_after = Pt(10)
        if has_img and k != 1:
            w, h = Image.open(img).size
            max_w, max_h = Inches(6.0), Inches(4.9)
            scale = min(max_w / w, max_h / h)
            sl.shapes.add_picture(str(img), Inches(6.9), Inches(1.9), width=int(w * scale), height=int(h * scale))
        foot = sl.shapes.add_textbox(Inches(0.7), Inches(6.95), Inches(11.9), Inches(0.4)).text_frame
        foot.paragraphs[0].text = f"TrueLift · {s.source}" if s.source else "TrueLift"
        foot.paragraphs[0].font.size = Pt(10)
        foot.paragraphs[0].font.color.rgb = rgb(MUTED)
        notes = list(s.notes) + [f"{r}: {t}" for r, t in s.registers.items()]
        sl.notes_slide.notes_text_frame.text = "\n\n".join(notes)
    prs.save(str(out))


def main() -> int:
    ss = slides()
    files = {
        OUT / "deck.html": deck_html(ss),
        OUT / "speaker_notes.md": notes_md(ss),
        OUT / "one_page.html": one_page_html(ss),
    }
    if "--check" in sys.argv[1:]:
        stale = [p.name for p, text in files.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
        if stale:
            print(f"pitch files out of date: {', '.join(stale)}; run python scripts/make_deck.py --pdf")
            return 1
        print("pitch files checked")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    for p, text in files.items():
        p.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {', '.join(p.name for p in files)} ({len(ss)} slides)")
    if "--pdf" in sys.argv[1:]:
        with tempfile.TemporaryDirectory(prefix="truelift-deck-") as tmp:
            shots = Path(tmp)
            keep = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--shots=")), None)
            if keep:
                shots = Path(keep)
                shots.mkdir(parents=True, exist_ok=True)
            print_pdf(OUT / "deck.html", OUT / "TrueLift_deck.pdf", 1280, 720, shots)
            print_pdf(OUT / "one_page.html", OUT / "TrueLift_one_page.pdf", 794, 1123)
            build_pptx(ss, shots, OUT / "TrueLift_deck.pptx")
        print("wrote TrueLift_deck.pdf, TrueLift_one_page.pdf, TrueLift_deck.pptx")
    return 0


if __name__ == "__main__":
    sys.exit(main())
