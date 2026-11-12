# TrueLift: Round 2 plan

Team Banana (IIT Gandhinagar): Yash Goyal, Bhavay Goyal, Kshitish Madbhavi. Updated 12 Nov 2026.

**In one line:** restaurant discounts on Zomato are judged by the orders that *use* them, not the
orders they *create*. TrueLift forecasts, targets and measures every restaurant-funded offer by
the extra orders and profit it creates, inside the offer flow Zomato already has: the owner's OTP
approval.

---

## 1. What we checked since Round 1

| What | Why it matters | Source |
|---|---|---|
| Zomato agreed that restaurant-funded campaigns are opt-in, approved by OTP before they start, and that past deductions would be reviewed outlet by outlet | Every restaurant-paid discount now needs the owner's yes, so owners need to know whether a discount pays | Angel One, 8 Aug 2026 |
| Bengaluru Hotels Association also asked that consent last only for an agreed period, that extensions need fresh approval, and that payouts be itemised | TrueLift's 4-week approval, renewal with a new OTP and itemised payout follow these demands | Angel One, The Week (Jul–Aug 2026) |
| Food delivery Q2 FY27: order value ₹11,445 Cr (+21.5%), adjusted EBITDA 5.5% of order value, 28.0M monthly customers | Zomato's own margin per order is thin, so wasted discount money matters | Eternal Q2 FY27 shareholder letter |
| 334,000 active restaurant partners | The scale TrueLift would serve | MediaNama, Q2 FY27 |
| Eternal's advertising and sales promotion spend: ₹1,138 Cr in Q2 FY27, up 41% from ₹806 Cr a year earlier | Discounting is rising again, so measuring what it buys is worth more | Q2 FY27 results table |
| "A customer who shows up only for a deep discount uses the same capacity as one who orders every week… those customers usually leave when the discount ends" (Albinder Dhindsa, Q2 letter, on Blinkit) | Eternal's leadership already thinks in terms of who a discount really brings in | Q2 FY27 letter |
| "Over 65% of Zomato app opens are exploratory… users browse an average of 12 menus" | Many visitors are undecided: that is where a discount can change the choice | Q2 FY27 letter |
| Swiggy put ~100 basis points of order value into prices "tailored to particular customer groups, to win back lapsed users" (Instamart, Q2 FY27) | Competitors already target discounts by group | Business Today, 26 Oct 2026 |
| Swiggy's "Discount Self Serve" lets ~1 lakh restaurants set discounts, pick customer segments and track performance | Targeting by segment and redemption reports already exist; measuring what a discount *caused* does not | Swiggy blog, Apr 2024 |
| Zomato "Brand Packs" reward repeat orders (4,000+ restaurants at launch) | The regulars' reward already exists; TrueLift uses it instead of inventing one | Business Standard, Jul 2024 |
| Ola and Uber received consumer-authority notices over alleged phone-based price differences; the minister said food delivery would be looked at | Targeting must never use device, payment method or inferred income | Business Standard, Jan 2025 |
| Meituan's MT-LIFT (5.5M randomised food-delivery coupon records): its download links are broken (open GitHub issues, Nov 2025 and Apr 2026), and one issue reports feature differences between coupon and no-coupon groups | Not usable now; we validate on Criteo's open incrementality data instead | GitHub MTDJDSP/MT-LIFT issues #2–#4 |
| Criteo uplift benchmark: 14M users from ad incrementality tests (a random 15% held out of ads), open download | A real randomised test of the same holdout idea; proves targeting, not rupee profit | Hugging Face criteo/criteo-uplift; Diemert et al., AdKDD 2018 |

Not found: any report on what happened after the 1 September deadline, or how the OTP flow looks
today. These are questions for Eternal (section 10).

## 2. The problem, with the numbers

**One ₹400 order** (25% commission + 18% GST on it = 29.5%; food and packaging 37%):

| | Full price | ₹60 off, paid by the restaurant |
|---|---|---|
| Food sales | ₹400 | ₹400 |
| Discount | – | −₹60 |
| Commission (25% of the bill) | −₹100 | −₹85 (25% of ₹340) |
| GST on commission (18%) | −₹18 | −₹15.30 |
| Food and packaging (37%) | −₹148 | −₹148 |
| **Restaurant keeps** | **₹134** | **₹91.70** |
| Zomato's gross commission | ₹100 | ₹85 |

**When a discount pays for itself.** Of the orders that use a discount, let *f* be the share that
would not have happened without it. The restaurant gains on those and loses ₹134 − ₹91.70 on all
the others. It breaks even when

    f × ₹91.70 > (1 − f) × (₹134 − ₹91.70)  →  f > 1 − 91.70/134 = 31.6%

| Discount on a ₹400 order | Restaurant keeps | Pays only if at least this share of its orders are extra |
|---|---|---|
| 10% (₹40) | ₹105.80 | 21% |
| 15% (₹60) | ₹91.70 | 32% |
| 20% (₹80) | ₹77.60 | 42% |
| 25% (₹100) | ₹63.50 | 53% |

If commission is charged on the bill *before* the discount (third-party calculators disagree),
₹60 off leaves ₹74 and the break-even rises to 45%.

**Why no report can show this.** A redemption report shows how many orders used the offer and the
sales they brought. *f* needs what would have happened without the offer, which only a comparison
group can show. So owners approve blind, and Zomato cannot tell owners which offers to keep.

**The Round 1 example, exact** (70 regular orders a week; a ₹60-off offer for everyone brings 30
new orders):

- Today: restaurant 100 × ₹91.70 − 70 × ₹134 = **−₹210 a week**; Zomato 100 × ₹85 − 70 × ₹100 = +₹1,500.
  ₹6,000 of discounts for 30 extra orders = ₹200 per extra order. Owners stop approving.
- TrueLift (discount only for new customers, ₹650 of Brand Pack rewards for regulars):
  restaurant 30 × ₹91.70 − ₹650 = **+₹2,101**; Zomato 30 × ₹85 = **+₹2,550**; ₹82 per extra order.
- The Round 1 page rounded 29.5% to 30% (−₹240 and +₹2,050). Gross commission is not Zomato's
  profit: after delivery costs its food business earns about 5.5% of order value (adjusted EBITDA).

## 3. What exists, and the gap

Zomato and Swiggy already let restaurants create offers, pick segments (new, repeat, lapsed),
reward repeat customers (Brand Packs) and see redemption reports. Zomato now asks for an OTP.
Missing everywhere: **what the offer caused**, before approval (forecast) and after (measurement),
and a rule for who should pay based on who gained.

## 4. How TrueLift works (four hooks in Zomato's offer flow)

| Step | Where in Zomato | What TrueLift does | Endpoint |
|---|---|---|---|
| 1. Before approval | Offer-creation and OTP screen | Forecast extra orders and profit (with a range) for the owner's offer; compare 34 versions of it and suggest a better one | `POST /api/quote` |
| 2. While it runs | Menu page, when a customer opens it | Show the discount only to customers it is expected to bring in; a random 10% of eligible customers never see it | `GET /api/serve` |
| 3. Who pays | Payout statement | Restaurant pays for its own offer; itemised payout; Zomato co-funds only where its own measurement shows a gain | payout lines in `run_week` |
| 4. Every week | WhatsApp + partner app | Measured extra orders and profit with a range; keep, change or stop; auto-pause when clearly losing; renewal after 4 weeks needs a new OTP with the evidence | `GET /api/offers/{id}` |

**Step 1, the forecast.** For each customer who visited the menu in the last two weeks, the uplift
model gives the chance of ordering without the offer (p0) and with it (p1). Then per week:

    extra orders   = Σ over shown visits (p1 − p0)
    extra profit   = Σ over shown visits (p1 × profit with offer − p0 × profit without)
    orders using it = Σ p1 × (share who use it: below 100% when there is a minimum order)

The range is the model's calibrated error (section 6). Versions compared, all at the owner's
discount size: with or without a minimum order (1.15 × the average order, e.g. ₹499) × 4 audiences
(everyone, new to the restaurant, stopped ordering 4+ weeks, targeted) × all day or 3–6 pm × with
or without a Brand Pack reward = 32, plus "no offer" and "Brand Pack only". The discount size stays
the owner's choice (section 6 explains why).

**Minimum orders.** Not every shown customer uses a minimum-order offer. A customer whose usual
basket b is below the minimum M uses a ₹D offer only if D > (1 − v) × (M − b), where v is how much
of a top-up they value. TrueLift learns v from past minimum-order offers (0.60 here; the
simulator's hidden value is 0.50) and forecasts the share who use the offer and their baskets.

**Step 2, who sees it.** Show the discount to a visitor only if p1 × ₹91.70 > p0 × ₹134 (for ₹60 off
a ₹400 order), i.e. only if the offer raises their chance of ordering by more than 46%. The rule
uses order history only: orders here, orders on Zomato, weeks since the last order, share of past
orders that used a discount, menu visits. Never device, payment method, location wealth or
anything that proxies ability to pay. The holdout is a hash of (customer, offer), so a held-out
customer stays held out for the offer's life and sees normal menu prices, never higher ones.

**Step 4, measuring a small restaurant.** A 10% holdout alone is too small. Example: 1,000 eligible
visits a week, 7% order without the offer and 10% with it (+3 points):

| Data used | 95% range of the measured lift |
|---|---|
| 10% holdout, 1 week | ±5.4 points (cannot tell if it works) |
| 10% holdout, 4 weeks | ±2.7 points |
| 20% holdout, 4 weeks | ±2.1 points |
| 50 similar restaurants pooled, 1 week | ±0.8 points |

So TrueLift combines the restaurant's own control group with the model learned from all
restaurants, weighting each by how precise it is:

    estimate = w × (own shown − held-out difference) + (1 − w) × model's estimate
    w = σ²_model / (σ²_model + se²_own)

In week 1 the model dominates; as the restaurant's own evidence grows, w rises. σ_model is set
from past offers with holdouts, using a model that never saw that restaurant (cross-fitting).

**Funding.** Restaurant-funded offers are the default (the OTP case). The simulator shows that
Zomato paying half the discount for customers new to Zomato, without measuring its own gain,
costs Zomato far more than it brings in (section 6). So Zomato should co-fund only where a
platform-level holdout shows new customers it would not otherwise get, and pay per measured extra
customer, not per redemption.

## 5. The prototype

- **Live demo:** https://yashg1836.github.io/truelift/ (static copy for three restaurants; every
  answer was precomputed by the real service). The full service runs locally (README).
- **Service** (`truelift/api.py`): the hooks above as a FastAPI app. A quote with 34 versions
  compared takes about 35 ms on a laptop (under 0.2 s under load); a serving decision for one
  customer takes about 1.5 ms and falls back to the owner's own audience rule if anything fails.
- Restaurants are real Bengaluru listings (name, locality, cuisine, rating, price). Their customers,
  orders and profits are simulated, and every screen carries a "simulated data" label.
- **Partner-app screens** (`truelift/static/`): home → create offer with a live forecast and a
  better version → OTP approval that records what the owner was shown → weekly results (today's
  report vs TrueLift's measurement, range, WhatsApp text, itemised payout) → keep or stop.
- **Inside Zomato panel**: real visitors of the restaurant (synthetic people) and whether each sees
  the discount, the simulator's true effect next to TrueLift's estimate, and the hook call log.
- **Evidence and money pages**: the results below and the calculations above.

## 6. Evidence from the simulated market

**Set-up.** 300 real Bengaluru delivery restaurants (Zomato listings: name, locality, cuisine,
cost for two, rating) in 6 localities; 30,000 synthetic customers of four hidden types (loyal,
casual, deal-seeker, infrequent). Each time a customer wants food they look at 8 menus and pick one
restaurant, Swiggy, or nothing (a standard choice model). Because the simulator knows every
customer's chance of ordering with and without each discount, it knows the true effect of every
offer. The models never see the hidden types, only order history, as Zomato would.

History: 4 weeks of today's market (40% of restaurants run blanket offers) plus 4 weeks of a
"shadow phase" in which offers vary at random with a 10% holdout. That is all the models learn from.
Then every policy runs for 4 weeks on the same customer visits. Numbers are true expected values,
per week, across all 300 restaurants.

**Results (base case)**

| Per week, 300 restaurants | Today: same discount (~15% of order) for everyone | Rule: new customers only | TrueLift |
|---|---|---|---|
| Offers that pay for themselves | 130 of 300 | 211 of 300 | **242 of 300** |
| Profit the offers create for their own restaurants | ₹6.94 lakh | ₹7.34 lakh | **₹7.65 lakh** |
| Restaurant profit vs no offers, whole market | +₹2.46 lakh | +₹3.96 lakh | **+₹4.85 lakh** |
| Orders that used a discount | 21,526 | 13,503 | 10,780 |
| …of which would have come anyway | 60% | 49% | **46%** |
| Discount given to customers | ₹16.7 lakh | ₹10.8 lakh | **₹10.0 lakh** |
| Average order value | ₹533 | ₹521 | **₹542** |
| Zomato's gross commission vs no offers | +₹6.45 lakh | +₹5.95 lakh | +₹6.38 lakh |
| Zomato contribution (8.5% of bill) vs no offers | +₹2.19 lakh | +₹2.02 lakh | +₹2.17 lakh |
| Loyal customers' visits going to Swiggy (no offers: 9.3%) | 7.7% | 8.6% | 8.8% |

TrueLift's numbers include the cost of its own 10% holdout; the other two do not measure anything.

What this says:
- **For restaurants:** 242 of TrueLift's offers pay for themselves, against 130 blanket offers.
  Market-wide, restaurants make about twice the extra profit of blanket offers while giving 40%
  less discount (₹10.0 lakh vs ₹16.7 lakh a week).
- **For Zomato:** gross commission is within 1% of blanket offers (+₹6.38 lakh vs +₹6.45 lakh) and 7%
  above the rule, with a higher average order value (₹542). Under the OTP rule this matters more:
  170 of the 300 blanket offers lose their restaurant money, and an owner who sees that declines
  the next OTP. TrueLift's commission comes from offers that owners have a reason to renew.
- **For customers:** the discount goes to people it changes the decision for. Loyal customers
  move slightly more to Swiggy than under blanket offers (8.8% vs 7.7% of their visits) and less
  than with no offers (9.3%). This is the regulars' trade-off. Brand Pack rewards only pay where
  regulars are price-sensitive, and the engine chose them at just 3 restaurants in this market.
- **Zomato co-funding, unmeasured:** paying half the discount for customers new to Zomato cost Zomato
  ₹5.0 lakh a week for about 70 more orders than TrueLift alone, turning its contribution from
  +₹2.17 lakh to −₹2.87 lakh. Zomato's own discount money needs the same measurement.

**One thing the model should not decide.** When the model also chose the discount size, profit
from the offers fell to ₹6.48 lakh, below the simple rule. Past offers vary the size only between
restaurants, too little to learn how a restaurant's customers respond to ₹40 vs ₹80, and picking
the best of many uncertain forecasts favours the over-estimated ones. So TrueLift keeps the owner's
discount size and decides who sees it, the minimum order, the time slot and the Brand Pack. A size
change should come from a depth test (customers randomly get one size or the other).

**If customers are more or less price-sensitive (±30%)**

| Scenario | Offers that pay: today / rule / TrueLift | Profit from own offers: today / rule / TrueLift | Restaurant profit vs no offers: today / rule / TrueLift | Zomato commission vs no offers: today / rule / TrueLift |
|---|---|---|---|---|
| Less price-sensitive | 70 / 130 / **193** | ₹2.16 / **₹3.47** / ₹3.21 lakh | −₹1.06 / +₹1.07 / **+₹1.91** lakh | ₹3.30 / ₹3.31 / ₹3.19 lakh |
| Base case | 130 / 211 / **242** | ₹6.94 / ₹7.34 / **₹7.65** lakh | +₹2.46 / +₹3.96 / **+₹4.85** lakh | ₹6.45 / ₹5.95 / ₹6.38 lakh |
| More price-sensitive | 181 / 245 / **258** | ₹11.62 / ₹11.26 / **₹11.78** lakh | +₹6.03 / +₹6.99 / **+₹7.75** lakh | ₹9.64 / ₹8.73 / ₹9.36 lakh |

TrueLift has the most paying offers and the highest market-wide restaurant profit in every case.
When customers barely respond to discounts, the simple rule creates slightly more profit from its
own offers (₹3.47 vs ₹3.21 lakh); blanket offers then lose restaurants money overall.

**Does the model find who a discount moves?** On the evaluation weeks, the predicted uplift per
visit correlates 0.59 with the true uplift, and the Qini score is 0.29 (0 = random ranking). In a
separate test with one fixed discount, model targeting captured about 60% of the profit a perfect
oracle could add over blanket offers (₹4.75 lakh vs ₹4.12 lakh; oracle ₹5.17 lakh).

**On real data, not just the simulator.** The same model, trained on 3 million users of Criteo's
open incrementality tests (real randomised holdouts from advertising), ranked 4.2 million users it
had never seen:

| Outcome | Rate with ads vs held out | Qini: TrueLift's model | Qini: random | Share of all the extra outcomes found in the top 30% the model picks |
|---|---|---|---|---|
| Visits | 4.86% vs 3.81% | **0.34** | 0.005 | **84%** |
| Purchases (rare) | 0.31% vs 0.18% | **0.06** | 0.015 | **67%** |

In words: if a campaign could only reach 30% of people, the model's choice of who would capture 84%
of all the extra visits the full campaign creates. This is advertising, not food discounts, so it
supports the method, not Zomato's numbers. (`scripts/validate_uplift.py criteo`)

**Are the weekly numbers right?**

For each of the 300 TrueLift offers we compare its running estimate of extra profit with the
true value. "Control group only" uses just the restaurant's 10% holdout; "model only" uses just
the model learned from all restaurants; TrueLift combines them. Errors are on cumulative extra
profit (true average per offer: ₹2,533 after 1 week, ₹5,091 after 2, ₹10,200 after 4).

| After | Truth inside the 80% range | Average error: control group only | Model only | TrueLift | "Keep" verdicts that were right | "Too early to say" |
|---|---|---|---|---|---|---|
| 1 week | 67% | ₹1,668 | ₹1,071 | **₹964** | 124 of 143 (87%) | 157 |
| 2 weeks | 79% | ₹2,443 | ₹2,178 | **₹1,525** | 108 of 120 (90%) | 180 |
| 4 weeks | 81% | ₹3,670 | ₹4,352 | **₹2,567** | 112 of 122 (92%) | 178 |

- The combined estimate beats both parts every week: in week 1 its error is 42% below the control
  group's alone.
- In week 1 the range is a little too narrow (67% instead of 80%); from week 2 it is right.
- About half the offers stay "too early to say" for four weeks. For a restaurant with ~50 orders a
  week that is the honest answer, and it is why TrueLift never auto-pauses on thin evidence.
- Each visit's predicted no-offer outcome is subtracted before comparing shown and held-out
  customers. This keeps the comparison unbiased and cut its noise by about 27% in our tests.
- Every policy is evaluated on the same simulated weeks and the same holdout draw, so that policies
  are compared on identical customers. The small average over-estimate in this run (+₹213 after
  week 1) is that one draw; across 10 different draws the average error was zero within noise.

## 7. Round 2 research we can do now (this week)

Talk to 6–8 restaurant owners on Zomato near campus (Gandhinagar/Ahmedabad). Ask for screenshots,
with customer details hidden.

1. What does your offer report show after an offer ends? (screenshot)
2. How do you decide to keep or stop an offer?
3. Have you approved an offer by OTP? What did that screen show?
4. Roughly what share of your Zomato orders come from repeat customers?
5. Do you use Brand Packs? Did they bring repeat orders?
6. On your payout statement, is commission charged on the bill before or after the discount?
7. Would "likely +₹1,600 to +₹2,500 a week" change your decision? Would you accept 1 in 10
   customers not seeing your offer so you can see what it really added?

## 8. Demo script (about 5 minutes)

1. **The problem (45 s).** Burger King, Jayanagar (simulated data on a real listing): ₹420 average
   order. Show the break-even table: ₹60 off pays only if 32 of every 100 orders using it are extra.
2. **Before approval (60 s).** Create "₹60 off for everyone": the forecast says about 70% of the
   orders using it would come anyway and the extra profit is about ₹0. TrueLift suggests "₹60 off
   only for customers it brings in" at about +₹1,700 a week; tap "Use this version". Domino's
   (blanket loses money) and Empire (blanket works, TrueLift doubles it) are in the dropdown.
3. **Consent (30 s).** OTP screen: what the owner approves, for how long, who pays. The consent
   record stores the forecast they saw.
4. **While it runs (60 s).** Inside Zomato: a regular doesn't get the discount (they'd order anyway),
   a lapsed customer does, one customer is in the control group.
5. **Every week (60 s).** Simulate four weeks: the report-vs-TrueLift card, the range narrowing as the
   restaurant's own evidence grows, the simulator's true value inside the range, WhatsApp text,
   itemised payout.
6. **Does it hold up (45 s).** Evidence tab: across 300 restaurants, offers that pay, profit,
   Zomato's commission, the real-data check on Criteo (top 30% picks hold 84% of the extra visits),
   measurement accuracy, and what the simulation does not prove.

If a judge opens Empire Restaurant: its weekly estimate runs high and the true value falls below
the range in all four weeks, while the verdict ("making money: keep") is right. Say so plainly: the
ranges are built to miss about 1 time in 5 (79–81% coverage from week 2), and this is one of them.
Burger King's true value is inside its range every week.

## 9. Questions judges will ask

- **"Isn't this just discount targeting? Swiggy has segments."** Segments decide who *can* see an
  offer; nobody measures what it *caused*. In our test the simple "new customers only" rule is a
  strong baseline, and TrueLift is compared against it, not only against blanket offers.
- **"Won't hiding the offer from 10% lose sales?"** Held-out customers pay normal menu prices;
  they are customers who would have got a discount. The holdout costs nothing in discount and is
  the only way to know what the offer added.
- **"A small restaurant can't measure anything in a week."** Correct, see the precision table. That
  is why the estimate starts from the model and shifts to the restaurant's own data over time,
  always shown as a range.
- **"Is personalised discounting legal?"** Only order history is used, never device or wealth
  proxies; held-out customers see normal prices, never higher ones; every rule is explainable.
- **"Does Zomato lose commission if discounts shrink?"** Blanket offers create more orders this week
  but lose money for many restaurants, and those owners now just decline the OTP. Offers that pay
  get approved again; Zomato's own discount spend can be measured the same way.
- **"Why should we trust a simulator?"** Because it knows the truth, it is the only place to check
  the method end to end. Results are shown under different assumptions, and the next step is a
  silent test on Zomato's own offer logs.

## 10. Questions for Eternal

1. Is the OTP approval live for all restaurant-funded offers? What does the screen show today?
2. Is commission charged on the bill before or after the discount? (break-even 32% vs 45% at 15% off)
3. Does Zomato run holdouts for its own discounts? Could we get anonymised offer logs for one
   city, or run TrueLift in shadow mode on them?
4. How do Brand Packs perform: repeat rate of members vs non-members?
5. For co-funded offers, how is Zomato's share decided today?
6. What latency budget does the menu page allow for an offer decision?

## 11. Limits

- The market is simulated. Customer types, price sensitivity and the Swiggy option are our
  assumptions, varied ±30%. Real numbers need Zomato's data.
- Long-term effects (a new customer becoming a regular, regulars drifting to Swiggy over months)
  are not modelled; measuring them needs longer holdouts.
- The real-data check (Criteo) is advertising, with no rupee outcome. Meituan's food-delivery
  coupon data (MT-LIFT) would be closer, but its download links are broken; the script also runs
  on it if a copy turns up.

## Sources

- Angel One, "Swiggy, Zomato agree to consent-based discounts…", 8 Aug 2026: https://www.angelone.in/news/market-updates/swiggy-zomato-agree-to-consent-based-discounts-bengaluru-hotel-bodies-defer-boycott-to-september-1-2026
- The Week, 30 Jul 2026: https://www.theweek.in/news/biz-tech/2026/07/30/wont-take-orders-anymore-why-bengaluru-restaurants-are-threatening-to-boycott-zomato-swiggy.html
- Eternal Q2 FY27 shareholder letter: https://b.zmtcdn.com/investor-relations/Eternal_Limited_Shareholders_Letter_Q2FY27_Results.pdf
- MediaNama, Q2 FY27: https://www.medianama.com/2026/10/223-eternal-125-crore-profit-q2fy27/
- Business Today, Swiggy Q2 FY27, 26 Oct 2026: https://www.businesstoday.in/latest/corporate/story/swiggys-discount-dilemma-is-back-focus-on-growth-or-profitability-563694-2026-10-26
- Swiggy blog, Discount Self Serve, Apr 2024: https://blog.swiggy.com/?p=18470
- Business Standard, Brand Packs, Jul 2024: https://www.business-standard.com/companies/news/zomato-rolls-out-brand-packs-to-reward-repeat-orders-from-restaurants-124072600697_1.html
- Business Standard, CCPA notices to Ola and Uber, Jan 2025: https://business-standard.com/industry/news/ccpa-issues-notices-to-ola-uber-over-differential-pricing-practice-125012301247_1.html
- Inc42, customer contact sharing after consent: https://inc42.com/buzz/zomato-to-share-customer-contact-with-restaurants-only-after-consent-ceo-mangla
- MT-LIFT: https://github.com/MTDJDSP/MT-LIFT (issues: https://github.com/MTDJDSP/MT-LIFT/issues)
- Criteo uplift dataset: https://huggingface.co/datasets/criteo/criteo-uplift ; paper: https://openreview.net/pdf?id=Q83-QeTB9lS
- FunnelCausalNet (notes MT-LIFT has no spend labels): https://arxiv.org/pdf/2608.11675
- Kaggle, Zomato Bangalore Restaurants: https://www.kaggle.com/datasets/himanshupoddar/zomato-bangalore-restaurants
