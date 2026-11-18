# TrueLift: method and evidence

Team Banana (IIT Gandhinagar): Yash Goyal, Bhavay Goyal, Kshitish Madbhavi. Updated 15 November 2026.

**In one line:** restaurant discounts on Zomato are judged by the orders that *use* them, not the
orders they *create*. TrueLift forecasts, targets and measures every restaurant-funded offer by the
extra orders and profit it creates, inside the offer flow Zomato already has: the owner's OTP
approval.

Restaurant names and listing details are real public 2019 listings; every customer, order and
profit figure is simulated. Every number below is generated from the files in `reports/` and
checked against them (`docs/claims.yml`, `scripts/check_claims.py`).

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
| Swiggy put about 100 basis points of order value into prices "tailored to particular customer groups, to win back lapsed users" (Instamart, Q2 FY27) | Competitors already target discounts by group | Business Today, 26 Oct 2026 |
| Swiggy's "Discount Self Serve" lets about 1 lakh restaurants set discounts, pick customer segments and track performance | Targeting by segment and redemption reports already exist; measuring what a discount *caused* does not | Swiggy blog, Apr 2024 |
| Zomato "Brand Packs" reward repeat orders (4,000+ restaurants at launch) | The regulars' reward already exists; TrueLift uses it instead of inventing one | Business Standard, Jul 2024 |
| Ola and Uber received consumer-authority notices over alleged phone-based price differences; the minister said food delivery would be looked at | Targeting must never use device, payment method or inferred income | Business Standard, Jan 2025 |
| Meituan's MT-LIFT (5.5M randomised food-delivery coupon records): its download links are broken (open GitHub issues) | Not usable now; we check the method on Criteo's and Hillstrom's open randomised data instead | GitHub MTDJDSP/MT-LIFT issues #2–#4 |

Not found: any report on what happened after the 1 September deadline, or how the OTP flow looks
today. These are questions for Eternal (section 10).

## 2. The problem, with the numbers

**One ₹400 order** (25% commission + 18% GST on it; food and packaging 37%). Computed by
`truelift/economics.py`, the same code the service uses:

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
would not have happened without it. The restaurant gains its discounted profit on those and loses
the difference on all the others, so it breaks even when f = 1 − ₹91.70 / ₹134 = 31.6%.

| Discount on a ₹400 order | Pays only if at least this share of its orders are extra |
|---|---|
| 10% (₹40) | 21% |
| 15% (₹60) | 32% |
| 20% (₹80) | 42% |
| 25% (₹100) | 53% |

If commission is charged on the bill *before* the discount (third-party calculators disagree), ₹60
off leaves ₹74 and the break-even rises to 45%.

**Percentage offers.** Most offers on Zomato are written as "40% off up to ₹80". The rupees off
depend on the order: 40% of a ₹150 order, but never more than ₹80, so from ₹200 up every order gets
₹80 off. The headline percentage is paid only on small orders, where the restaurant keeps least:
such an offer pays only if 84% of the ₹150 orders using it are extra, against 42% of the ₹400 ones
and 28% of the ₹600 ones. The Money page shows the calculation.

**Why no report can show this.** A redemption report shows how many orders used the offer and the
sales they brought. *f* needs what would have happened without the offer, which only a comparison
group can show. So owners approve blind, and Zomato cannot tell owners which offers to keep.

**The Round 1 example, exact** (70 regular orders a week; a ₹60-off offer for everyone brings 30
new orders): the restaurant makes −₹210 a week and Zomato's commission rises by ₹1,500; ₹6,000 of
discounts buy 30 extra orders, ₹200 per extra order. With the discount only for the new customers
and ₹650 of Brand Pack rewards for regulars, the restaurant makes +₹2,101 and Zomato +₹2,550, ₹82
per extra order. Gross commission is not Zomato's profit: after delivery costs its food business
earns about 5.5% of order value (adjusted EBITDA).

## 3. What exists, and the gap

Zomato and Swiggy already let restaurants create offers, pick segments (new, repeat, lapsed),
reward repeat customers (Brand Packs) and see redemption reports. Zomato now asks for an OTP.
Missing everywhere: **what the offer caused**, before approval (forecast) and after (measurement),
and a rule for who should pay based on who gained.

## 4. How TrueLift works

TrueLift has two layers. The **measurement layer** (a random control group and a weekly result) is
what makes anything else trustworthy, and it works even for an owner who keeps their own design.
The **decision layer** (the forecast, the better version, who sees the discount) uses a model
learned from all restaurants, and is checked every week by the measurement layer.

| Step | Where in Zomato | What TrueLift does | Endpoint |
|---|---|---|---|
| 1. Before approval | Offer-creation and OTP screen | Forecast extra orders and profit, with a range, for the owner's offer; compare about 34 versions of it at the same discount and suggest a better one, or no offer | `POST /api/v1/quote` |
| 2. While it runs | Menu page, when a customer opens it | Look up whether this customer sees the discount (a table built at approval); a random 10% of eligible customers never see it | `GET /api/v1/serve` |
| 3. Who pays | Payout statement | The restaurant pays for its own offer; itemised payout; Zomato co-funds only where its own measurement shows a gain | payout lines of each week |
| 4. Every week | WhatsApp and partner app | Measured extra orders and profit with a range; keep, too early, probably losing, or pause; renewal after four weeks needs a new OTP and shows what was measured | `GET /api/v1/offers/{id}`, `POST /api/v1/offers/{id}/renew` |

**Step 1, the forecast.** For each customer who visited the menu in the last two weeks, with the
history they had at the time, the uplift model gives the chance of ordering without the offer (p0)
and with it (p1). Then per week, over the visits that would see it:

    extra orders    = Σ (p1 − p0)
    extra profit    = Σ (p1 × profit with the offer − p0 × profit without)
    orders using it = Σ p1 × (share who use it: below 100% when there is a minimum order)

The range is the model's error, measured on past offers that had a random holdout. The versions
compared all keep the owner's discount and format (flat or percentage): with or without a minimum
order, four audiences (everyone, new to the restaurant, stopped ordering for four weeks or more,
chosen by TrueLift), all day or 3–6 pm, with or without a Brand Pack reward, plus "no offer" and
"Brand Pack only". A version is suggested only if it has at least a 60% chance of making the owner
money; otherwise TrueLift says no version is likely to pay.

**What the promises are.** TrueLift does not promise a profit. It promises a forecast with an honest
range before the owner approves, a measurement of what the offer really added each week, and that
no offer is paused on the model's word alone: a pause needs the offer's own control group to show a
loss beyond a boundary that stays valid however often the owner looks.

**Minimum orders.** Not every shown customer uses a minimum-order offer. A customer whose usual
order b is below the minimum M uses a ₹D offer only if D > (1 − v) × (M − b), where v is how much of
a top-up they value. TrueLift learns v from past minimum-order offers on menu visits (it recovers
the simulator's hidden value exactly) and forecasts the share who use the offer and their orders.

**Step 2, who sees it.** A customer sees the discount only if it is expected to raise the
restaurant's profit from that visit. The model reads order history only: orders here and on Zomato,
weeks since the last order, share of past orders that used a discount, menu visits. Never device,
payment method, location below the city or anything that stands in for ability to pay
(`docs/privacy_and_fairness.md`). The holdout is a hash of (customer, offer), so a held-out
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
restaurants, each weighted by how precise it is:

    estimate = w × (own shown − held-out difference) + (1 − w) × model's estimate
    w = σ²_model / (σ²_model + se²_own)

In week 1 the model dominates; as the restaurant's own evidence grows, w rises. Both noise sizes are
re-estimated every week across all running offers: two random halves of each offer's customers
show the real noise of its own estimate, and the spread of own estimates around the model's shows
the model's real error. Neither needs the truth, so this works inside Zomato as it does here.

**Offer formats.** Flat ₹ off and percentage off with a cap are both supported end to end. A
percentage offer is scored by the model at its average discount per order that uses it; customers
in the simulator get their own bill's discount (decision record 0009). Item-level discounts and
"buy one get one" need item-level baskets, which the simulator does not have; free delivery funded
by the restaurant would be a flat saving with a different cost, and fits the same four hooks.

**Funding.** Restaurant-funded offers are the default (the OTP case). Zomato co-funding is shown as
a caution: paying part of the discount without changing who sees it only moves money from Zomato
to restaurants (section 6). Zomato should co-fund only where a platform-level holdout shows new
customers it would not otherwise get, and pay per measured extra customer, not per redemption.

## 5. The prototype

- **Live demo:** https://yashg1836.github.io/truelift/ : the service's own answers for 32
  restaurants (six localities, five price bands) and every design the create screen can produce.
  An offline bundle opens from a file with no network. The full service runs locally or in Docker
  (README).
- **Service** (`truelift/api.py`): the hooks above under `/api/v1`, with a typed contract
  (`docs/openapi.json`), problem-detail errors, per-visitor sessions, OTP expiry and attempt limits,
  a hash-chained consent ledger, an exposure log the measurement reads, health, readiness and
  metrics. Speeds are measured over HTTP (`reports/latency.json`, Evidence page).
- **Partner-app screens**: create an offer (flat or percentage) with a live forecast and a better
  version, OTP approval that records what the owner was shown, weekly results (today's report
  against TrueLift's measurement, the range, the evidence behind it, WhatsApp text, itemised
  payout), renewal on the measured result, and a "what if you had run your version" comparison.
- **Inside Zomato panel**: real visitors of the restaurant (synthetic people) and whether each sees
  the discount, the simulator's true effect next to TrueLift's estimate, and the call log.
- **Guided demo** (10 steps, Back and keys), **How it works**, **Evidence**, **Money maths** with
  switches for the commission base and food cost, and **Operations** (guardrails and drift).
- Restaurants are real Bengaluru listings; their customers, orders and profits are simulated, and
  every screen carries a "simulated data" label.

## 6. Evidence from the simulated market

**Set-up.** 300 real Bengaluru delivery restaurants (name, locality, cuisine, cost for two, rating)
in six localities; 30,000 synthetic customers of four hidden types (loyal, casual, deal-seeker,
infrequent). Each time a customer wants food they look at 8 menus and pick one restaurant, Swiggy,
or nothing (a standard choice model). Because the simulator knows every customer's chance of
ordering with and without each discount, it knows the true effect of every offer. The models never
see the hidden types, only order history, as Zomato would. Every assumption, and what would replace
it inside Zomato, is in `docs/simulator_datasheet.md`.

History: eight weeks of today's market (40% of restaurants run blanket offers) plus four weeks of a
shadow phase in which the offers owners run vary at random over the create screen's options, with a
10% holdout. That is all the models learn from. Then every policy runs for four weeks on the same
customer visits. Numbers are true expected values, per week, across all 300 restaurants.

**Results (base case)**

<!-- BEGIN:results-table -->
| | Today: same discount for everyone | Rule: new customers only | TrueLift |
|---|---|---|---|
| Offers that pay for themselves | 130 of 300 | 214 of 300 | **218 of 228** |
| Offers that lose money | 170 | 86 | **10** |
| Restaurants' profit from their own offers | +₹6.94 lakh | +₹7.16 lakh | **+₹7.89 lakh** |
| Restaurant profit vs no offers (market) | +₹2.46 lakh | +₹3.80 lakh | **+₹4.77 lakh** |
| Discount given | ₹16.71 lakh | **₹10.72 lakh** | ₹10.77 lakh |
| Zomato commission vs no offers | +₹6.45 lakh | +₹5.79 lakh | **+₹6.53 lakh** |
<!-- END:results-table -->

TrueLift's figures include the cost of its own 10% control group; the other two measure nothing.

- **For restaurants.** 218 of TrueLift's 228 offers pay for themselves, against 130 of 300 blanket
  offers; TrueLift advises no discount at the other 72 restaurants. Of the orders using a blanket
  offer, 60% would have come anyway; with TrueLift, 43%.
- **For Zomato.** Commission is higher than with blanket offers and the rule, because offers that
  pay keep running: across five market seeds TrueLift beats blanket offers on offers that pay,
  own-offer profit, market-wide restaurant profit and Zomato's commission in every seed, with about
  ₹6 lakh a week less discount (`seeds` in `reports/evaluation.json`). Under the OTP rule this
  matters more: 170 of the 300 blanket offers lose their restaurant money, and an owner who sees
  that declines the next OTP.
- **Whose orders they are.** Of the extra orders TrueLift's offers create, 52% are extra for Zomato
  as a whole (taken from Swiggy or from not ordering at all); the rest move from other restaurants
  on Zomato. For blanket offers the share is 48%.
- **Customers.** The discount goes to people it changes the decision for. Loyal customers move
  slightly more to Swiggy than under blanket offers (8.7% of their visits against 7.7%) and less than
  with no offers at all (9.3%). The Brand Pack reward for regulars, measured on its own, closes that
  gap at almost no cost (`docs/privacy_and_fairness.md`).
- **The control group's price.** Holding out one customer in ten gives up ₹87,664 of restaurant
  profit a week across the market (719 orders): the price of knowing what each offer adds.
- **Zomato co-funding, unmeasured.** Paying half the discount for customers new to Zomato, with the
  same customers shown the offer, costs Zomato ₹57,527 a week and creates no extra order: the
  customer sees the same offer whoever pays for it, so it is a transfer from Zomato to restaurants.

**Is the forecast right?** In today's market, where a restaurant switches while others keep their
offers (the condition a quote describes), TrueLift's forecasts add up to 82% of the true effect of
the versions it chose; 99% of the true effects fall inside the 80% ranges, and the sign is right
for 96% of offers. The ranges are therefore wide and the forecast cautious.

**Does the suggested version really beat the owner's?** For 79% of restaurants it does. The
suggested version's stated advantage over the owner's offer is about five times its true advantage
(₹1.45 lakh against ₹0.28 lakh a week across the market): picking the best of about 34 forecasts
favours the ones that came out high. The page therefore shows every suggestion's range and says
that the gain may be smaller in practice.

**One thing the model should not decide.** Letting the model also choose the discount size raises
restaurants' profit from their own offers from ₹7.89 lakh to ₹9.57 lakh a week, but across the
market by only ₹0.20 lakh, and the offers that lose money rise from 10 to 28
(`reports/exp_depth_choice.json`): deeper discounts mostly win orders from other restaurants. In the
shadow phase the size varies only between restaurant-weeks, never between customers of the same
restaurant in the same week, and choosing the best of several noisy forecasts overstates the gain.
So TrueLift keeps the owner's size and decides who sees the offer, the minimum order, the time slot
and the Brand Pack. A size change should come from a test that gives customers one size or another
at random; in the simulator four weeks of one restaurant's own data pick the truly better size 65%
of the time, and only 50% for the smaller half of restaurants (`reports/exp_depth_test.json`), so
such tests need pooling across similar restaurants or longer runs.

**If customers are more or less price-sensitive (±30%), or commission is charged before the discount**

<!-- BEGIN:scenario-table -->
| Scenario | Offers that pay: today / rule / TrueLift | Own-offer profit: today / rule / TrueLift | Restaurant profit vs no offers: today / rule / TrueLift | Zomato commission vs no offers: today / rule / TrueLift |
|---|---|---|---|---|
| Customers 30% less price-sensitive | 70 / 130 / 153 | ₹2.16 lakh / ₹3.39 lakh / ₹3.96 lakh | −₹1.06 lakh / +₹1.00 lakh / +₹2.23 lakh | +₹3.30 lakh / +₹3.24 lakh / +₹3.71 lakh |
| Base case | 130 / 214 / 218 | ₹6.94 lakh / ₹7.16 lakh / ₹7.89 lakh | +₹2.46 lakh / +₹3.80 lakh / +₹4.77 lakh | +₹6.45 lakh / +₹5.79 lakh / +₹6.53 lakh |
| Customers 30% more price-sensitive | 181 / 245 / 252 | ₹11.62 lakh / ₹10.95 lakh / ₹11.94 lakh | +₹6.03 lakh / +₹6.72 lakh / +₹7.67 lakh | +₹9.64 lakh / +₹8.47 lakh / +₹9.46 lakh |
| Commission on the price before the discount | 50 / 112 / 109 | ₹2.01 lakh / ₹4.00 lakh / ₹5.12 lakh | −₹2.47 lakh / +₹0.64 lakh / +₹2.77 lakh | +₹10.63 lakh / +₹8.47 lakh / +₹8.58 lakh |
<!-- END:scenario-table -->

The sweep of eight assumptions, each low and high (`reports/sensitivity.json`, the tornado chart on
the Evidence page), says in words where each claim stops holding.

**Percentage offers**

<!-- BEGIN:pct-table -->
| Format | Rupees off per use, share of the flat amount | Offers that pay: blanket / TrueLift | Own-offer profit: blanket / TrueLift | Restaurant profit vs no offers (market): blanket / TrueLift | TrueLift forecast against truth |
|---|---|---|---|---|---|
| Flat amount (as above) | 100% | 130 / 218 | +₹6.94 lakh / +₹7.89 lakh | +₹2.46 lakh / +₹4.77 lakh | 0.82 |
| Percentage up to the flat amount (cap reached from half the usual order) | 100% | 130 / 218 | +₹6.94 lakh / +₹7.89 lakh | +₹2.46 lakh / +₹4.77 lakh | 0.82 |
| 15% off up to twice the flat amount (discount follows the bill) | 105% | 146 / 223 | +₹8.15 lakh / +₹7.90 lakh | +₹3.46 lakh / +₹5.11 lakh | 1.07 |
<!-- END:pct-table -->

Written the usual way (the cap reached from half the usual order), a percentage offer behaves like a
flat offer of its cap, because few orders fall below the point where the cap applies. Where the
discount follows every bill ("15% off up to twice the flat amount"), blanket offers do much better
than flat ones for their own restaurants, and in total slightly better than TrueLift's versions;
but much of that gain is taken from other restaurants, so across the market restaurants keep more
with TrueLift, which also has far fewer offers that lose. A discount that follows the bill costs the
same share of every order's margin, while a flat one takes a bigger share of a small order's. The
model's single number (the average discount per use) still gives a fair forecast for TrueLift's
versions; blanket percentage offers are under-forecast more than flat ones.

**Are the weekly numbers right?** For each of TrueLift's offers we compare its running estimate of
extra profit with the true value. "Control group only" uses just the restaurant's 10% holdout;
"model only" uses just the model learned from all restaurants; TrueLift combines them.

<!-- BEGIN:measurement-table -->
| After | Truth inside the 80% range | Average error: control group only | Model only | TrueLift combined | "Keep" verdicts truly positive |
|---|---|---|---|---|---|
| 1 week | 79% | ₹1,975 | ₹655 | ₹642 | 140 of 142 |
| 2 weeks | 87% | ₹2,892 | ₹1,220 | ₹1,166 | 113 of 114 |
| 4 weeks | 90% | ₹4,160 | ₹2,212 | ₹2,054 | 111 of 111 |
<!-- END:measurement-table -->

- The combined estimate's error is below both parts' from week one.
- Placebo offers, which change nothing, were paused in 1.8% of cases over a four-week approval (the
  rule used before, "pause when the range is below zero", paused 18.4%), and in 2.2% over twelve
  weekly looks (32.0% before). A pause therefore means the offer's own customers show a loss.
- Each visit's predicted no-offer outcome is subtracted before comparing shown and held-out
  customers. This keeps the comparison unbiased and cuts the noise of an offer's own estimate by 6%
  (`reports/exp_variance_reduction.json`), less than the 27% we reported in Round 2 on a smaller test.
- Across ten random holdout draws, the four-week estimate over-states the truth by ₹452 an offer on
  average (standard error ₹89): a bias the estimate inherits from the model's forecast, which it
  leans on while an offer's own control group is small. Its 80% range still holds the truth 90% of
  the time (`reports/exp_holdout_draws.json`).

**Does the model find who a discount moves?** On the evaluation weeks the predicted uplift per visit
correlates 0.61 with the true uplift (Qini 0.23, where 0 is a random ranking). Over five simulated
markets, the T-learner TrueLift uses earns the most profit from its top 30% of any learner (78% of
the best possible), against 70% for ranking by who is likely to order anyway; the S-learner ranks
slightly better by Qini (`reports/learner_benchmark.json`). With one fixed discount everywhere, the
model's targeting captures 72% of what an oracle that knows every visit's true response could add
over blanket offers (`reports/exp_oracle.json`).

**On real data, not just the simulator.** The same method (one gradient-boosted model per group),
refitted on each dataset, ranked customers it had never seen in two public randomised experiments:
Criteo's advertising tests (14 million users, a random 15% held out of ads) and Kevin Hillstrom's
retail e-mail test (64,000 customers, with what they spent). Each figure is the share of the
campaign's total extra outcome found in the top 30% of the ranking, with its 90% range from 200
resamples of the test customers.

<!-- BEGIN:realdata-table -->
| Dataset and outcome | Random | Likely to act anyway | S-learner | T-learner (TrueLift) | X-learner |
|---|---|---|---|---|---|
| Criteo, ads: visits | 29% (27% to 31%) | 84% (83% to 86%) | 85% (83% to 87%) | 84% (82% to 86%) | 85% (83% to 87%) |
| Criteo, ads: purchases | 30% (26% to 33%) | 92% (90% to 94%) | 63% (59% to 68%) | 72% (67% to 76%) | 85% (82% to 89%) |
| Hillstrom, women's e-mail: visits | 23% (9% to 34%) | 45% (33% to 58%) | 55% (44% to 71%) | 53% (39% to 66%) | 54% (40% to 70%) |
| Hillstrom, women's e-mail: purchases | 17% (−50% to 60%) | 55% (3% to 136%) | 41% (−19% to 101%) | 65% (13% to 111%) | 28% (−36% to 67%) |
| Hillstrom, women's e-mail: spend | 28% (−27% to 64%) | 24% (−27% to 62%) | 49% (20% to 118%) | 36% (−9% to 86%) | 22% (−26% to 54%) |
| Hillstrom, men's e-mail: visits | 28% (21% to 34%) | 38% (32% to 46%) | 40% (32% to 46%) | 39% (32% to 45%) | 35% (29% to 43%) |
| Hillstrom, men's e-mail: purchases | 19% (−6% to 39%) | 17% (−23% to 40%) | 51% (24% to 81%) | 25% (−3% to 51%) | 58% (34% to 90%) |
| Hillstrom, men's e-mail: spend | 24% (−24% to 74%) | 29% (−3% to 93%) | 12% (−61% to 52%) | 28% (−6% to 71%) | 27% (−30% to 66%) |
<!-- END:realdata-table -->

The honest reading: on Criteo's visits every model, including the shortcut of ranking people by
how likely they are to act at all, finds about the same share; on Criteo's rare purchases the
shortcut does best and the X-learner beats TrueLift's T-learner. On Hillstrom's women's e-mail the
uplift models find more than the shortcut in all five random splits. On dollars spent no ranking is
reliably better than random with about 13,000 test customers per e-mail, which is why TrueLift
models the chance of an order and computes the money from each order's economics. Which ranking
works depends on the setting; inside Zomato the shadow phase's random holdout would score every
candidate before any is used (decision record 0006). Neither dataset is about food discounts: they
test the method, not Zomato's numbers.

## 7. Research with restaurant owners

The field kit in `docs/field_research/` (question sheets in English, Hindi and Gujarati, a consent
script, a note template, comprehension cards that compare today's offer report with TrueLift's
weekly result, and a target-outlet sheet) is ready. The first interview took place on 17 November
2026: a team member showed the demo to the manager of a chain outlet in Gandhinagar. Its note is not
written up yet, so the findings table in `docs/field_research.md` is still empty. We publish no
finding we have not collected.

## 8. Demo script (about 5 minutes)

1. **The problem (45 s).** Burger King, Jayanagar (simulated data on a real listing). Money maths:
   ₹60 off pays only if 32 of every 100 orders using it are extra; a "40% off up to ₹80" offer pays
   on a ₹150 order only if 84 of 100 are extra.
2. **Before approval (60 s).** Create "₹60 off for everyone": most orders using it would come anyway.
   TrueLift suggests a better version at the same discount, with its range; "Use this version".
3. **Consent (30 s).** OTP screen: what the owner approves, for how long, who pays. The consent record
   stores the forecast they saw.
4. **While it runs (60 s).** Inside Zomato: a regular does not get the discount (they would order
   anyway), a lapsed customer does, one customer is in the control group.
5. **Every week (60 s).** Simulate four weeks: today's report against TrueLift's measurement, the
   range narrowing as the restaurant's own evidence grows, "Show me how you know", WhatsApp text,
   payout. Renew on the measured result; see what the other version would have made.
6. **Does it hold up (45 s).** Evidence tab: offers that pay, profit, Zomato's commission, the
   seeds, measurement accuracy, the real-data checks including where the shortcut wins, and what the
   simulation does not prove.

The guided demo runs the same story with captions. If a restaurant's true value falls outside its
range in some week, say so plainly: the ranges are built to miss about one time in five.

## 9. Questions judges will ask

The full question bank, each answer with its number and source, is `docs/pitch/questions.md`.

- **"Isn't this just discount targeting? Swiggy has segments."** Segments decide who *can* see an
  offer; nobody measures what it *caused*. The simple "new customers only" rule is a strong baseline,
  and TrueLift is compared against it, not only against blanket offers.
- **"Won't hiding the offer from 10% lose sales?"** Held-out customers pay normal menu prices; they
  are customers who would have got a discount. The holdout gives up some extra orders, which the
  Evidence page prices, and it is the only way to know what an offer added.
- **"A small restaurant can't measure anything in a week."** Correct, see the precision table. That
  is why the estimate starts from the model and shifts to the restaurant's own data over time,
  always with a range.
- **"Is personalised discounting legal?"** Only order history is used, never device or wealth
  proxies; held-out customers see normal prices, never higher ones; our reading of the rules is in
  `docs/privacy_and_fairness.md`.
- **"Does Zomato lose commission if discounts shrink?"** No: in every market seed TrueLift's commission
  is above blanket offers', because offers that pay keep being approved.
- **"Why should we trust a simulator?"** Because it knows the truth, it is the only place to check the
  method end to end. Results hold across seeds and assumptions, the real-data checks are reported
  including where we lose, and the first phase inside Zomato is a shadow holdout on real offers
  (`docs/integration_blueprint.md`).

## 10. Questions for Eternal

1. Is the OTP approval live for all restaurant-funded offers? What does the screen show today?
2. Is commission charged on the bill before or after the discount? (Break-even 32% against 45% at 15% off.)
3. Does Zomato run holdouts for its own discounts? Could we get anonymised offer logs for one city,
   or run the shadow kit (`scripts/shadow_measure.py`) on them?
4. How do Brand Packs perform: repeat rate of members against non-members?
5. For co-funded offers, how is Zomato's share decided today?
6. What latency budget does the menu page allow for an offer decision?

## 11. Other businesses and the road ahead

The same four hooks answer the same question elsewhere in Eternal; only the first column of evidence
(food-delivery offers) exists here.

| Business | Who funds the discount | The question TrueLift would answer |
|---|---|---|
| Zomato restaurant ads | Restaurants pay for visibility | Did the ad bring orders that would not have come? |
| Blinkit brand-funded promotions | Consumer brands | Did the promotion add units, or pull purchases forward and from rival brands? |
| District (dining out, events) | Restaurants and organisers | Did the offer fill seats that would have been empty? |
| Zomato-funded coupons and Gold | Zomato | Which of Zomato's own discount rupees buy platform-new orders? |

Next steps, in order: a shadow holdout on real offers in one city; a randomised pilot of the forecast
and weekly result (`docs/integration_blueprint.md`, with its sample size); a long-run holdout of
about 1% of customers to measure what offers do to habits over a quarter; and following customers
an offer brought in for eight weeks, to decide whether acquisition offers that lose money in week
one are worth running.

**Comparable work.** Ad platforms measure campaigns with "ghost ads" and conversion-lift holdouts.
DoorDash, for example, measures what its restaurant ads add with ghost ads, and since March 2026
sells brands a Sales Lift Measurement product. Food-delivery researchers have also published
randomised coupon data (Meituan's MT-LIFT). TrueLift applies the same holdout idea to
restaurant-funded offers, puts the forecast where the owner decides (the OTP screen), and ties the
weekly result to renewal.

## 12. Limits, and what is not modelled

- The market is simulated. Customer types, price sensitivity and the Swiggy option are our
  assumptions, varied in the sensitivity sweep. Real numbers need Zomato's data.
- Not modelled: Swiggy reacting to TrueLift, restaurants' Swiggy-side offers, kitchen capacity,
  delivery fees, platform coupons stacking with restaurant offers, Zomato Gold, ratings feedback, and
  habits that change because of last week's discount.
- Long-term effects (a new customer becoming a regular, regulars drifting away over months) need
  longer holdouts.
- The real-data checks are advertising and e-mail, with one money outcome (dollars spent) that is too
  noisy to rank on. Meituan's food-delivery coupon data would be closer; its download links are
  broken.
- The suggested version's stated advantage runs well above its true advantage (section 6).

## Sources

- Angel One, "Swiggy, Zomato agree to consent-based discounts…", 8 Aug 2026: https://www.angelone.in/news/market-updates/swiggy-zomato-agree-to-consent-based-discounts-bengaluru-hotel-bodies-defer-boycott-to-september-1-2026
- The Week, 30 Jul 2026: https://www.theweek.in/news/biz-tech/2026/07/30/wont-take-orders-anymore-why-bengaluru-restaurants-are-threatening-to-boycott-zomato-swiggy.html
- Eternal Q2 FY27 shareholder letter: https://b.zmtcdn.com/investor-relations/Eternal_Limited_Shareholders_Letter_Q2FY27_Results.pdf
- MediaNama, Q2 FY27: https://www.medianama.com/2026/10/223-eternal-125-crore-profit-q2fy27/
- Business Today, Swiggy Q2 FY27, 26 Oct 2026: https://www.businesstoday.in/latest/corporate/story/swiggys-discount-dilemma-is-back-focus-on-growth-or-profitability-563694-2026-10-26
- Swiggy blog, Discount Self Serve, Apr 2024: https://blog.swiggy.com/?p=18470
- Business Standard, Brand Packs, Jul 2024: https://www.business-standard.com/companies/news/zomato-rolls-out-brand-packs-to-reward-repeat-orders-from-restaurants-124072600697_1.html
- Business Standard, CCPA notices to Ola and Uber, Jan 2025: https://business-standard.com/industry/news/ccpa-issues-notices-to-ola-uber-over-differential-pricing-practice-125012301247_1.html
- MT-LIFT: https://github.com/MTDJDSP/MT-LIFT (issues: https://github.com/MTDJDSP/MT-LIFT/issues)
- DoorDash Ads, "Measuring Restaurant Ads Incrementality with Ghost Ads": https://advertising.doordash.com/en-ca/resources/measuring-incrementality-with-ghost-ads-at-doordash
- DoorDash, "DoorDash Ads Launches Sales Lift Measurement", Mar 2026: https://about.doordash.com/en-us/news/doordash-ads-launches-sales-lift-measurement
- Criteo uplift dataset: https://huggingface.co/datasets/criteo/criteo-uplift ; paper: https://openreview.net/pdf?id=Q83-QeTB9lS
- Hillstrom, MineThatData E-Mail Analytics and Data Mining Challenge (2008): http://www.minethatdata.com/Kevin_Hillstrom_MineThatData_E-MailAnalytics_DataMiningChallenge_2008.03.20.csv
- Künzel, Sekhon, Bickel and Yu, "Metalearners for estimating heterogeneous treatment effects", PNAS 2019 (the X-learner).
- Kaggle, Zomato Bangalore Restaurants: https://www.kaggle.com/datasets/himanshupoddar/zomato-bangalore-restaurants
