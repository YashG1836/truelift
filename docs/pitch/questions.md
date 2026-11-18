# Question bank

Thirty questions a panel is likely to ask, each with a short answer, the number behind it and the
file it comes from. Every number here is checked against `reports/` by `scripts/check_claims.py`.
Customers, orders and profits are simulated (300 real 2019 Bengaluru listings, synthetic
customers); say so whenever a number is quoted.

How to answer: the number first, one sentence of meaning, then stop. If the honest answer is "we
do not know", say what would find out. One person answers; the others add only if asked. Each team
member owns ten questions and rehearses them without notes.

**Positioning, in one sentence.** DoorDash already measures what restaurant ads and brand
promotions add, with ghost-ads holdouts, and sells that proof to advertisers. Since August 2026
every restaurant-funded offer on Zomato needs the owner's OTP; TrueLift puts the same kind of
proof on the screen where the owner signs.

## Business

**1. Does this reduce our order volume?**
A little, against blanket offers that everyone keeps approving: 20,295 orders a week against
21,526, which is 6% fewer. That world needs owners to keep signing offers that lose 170 of them
money. If half of them stop approving blind, blanket orders fall to 19,376.
*Source: `reports/evaluation.json` (policies, consent_attrition).*

**2. What does Zomato earn?**
More commission than with blanket offers: +₹6.53 lakh a week against +₹6.45 lakh, in every one of
five market seeds, because order values are higher and less of each bill is discount. Contribution
moves the same way: +₹2.22 lakh against +₹2.19 lakh.
*Source: `reports/evaluation.json` (policies, seeds).*

**3. Aren't you just moving orders between our restaurants?**
Partly, and we measure it: 52% of TrueLift's extra orders are new to Zomato, against 48% for
blanket offers. The rest come from other restaurants on Zomato. Zomato's own money should follow
the platform-new part.
*Source: `reports/evaluation.json` (zomato_ledger).*

**4. Why would owners trust a number from the platform that charges them?**
Because it can tell them not to discount: TrueLift advises no offer at 72 of 300 restaurants. The
number comes from their own customers held out at random, and the consent record stores the
forecast they saw, so both can be audited.
*Source: `reports/evaluation.json` (selection); `truelift/store.py`.*

**5. What does it cost to run?**
A lookup per menu open (2.5 ms at the 95th percentile over HTTP on a laptop) and batch work for
quotes and weekly measurement. The real cost is the control group: ₹87,664 of restaurant profit a
week across 300 restaurants. That is the price of knowing.
*Source: `reports/latency.json`, `reports/evaluation.json` (zomato_ledger).*

**6. What do you need from us?**
Three things: whether commission is charged before or after the discount, anonymised offer logs
for one city to run the shadow kit on, and what the OTP screen shows today with how often owners
decline.
*Source: `docs/method_and_evidence.md` §10; `scripts/shadow_measure.py`.*

## Method

**7. Why trust a simulator?**
Because it knows the truth, so every forecast, range and verdict is checked against it, which no
real dataset allows. The results hold over five market seeds and eight assumptions swept low and
high, and we say where they stop holding. The method is also checked on real randomised data.
*Source: `reports/evaluation.json` (seeds), `reports/sensitivity.json`.*

**8. How accurate is the forecast?**
Cautious. For TrueLift's versions the forecasts add up to 82% of the true effect in today's
market and 100% once every restaurant has switched; for blanket offers, 68%. The 80% ranges hold
99% of the truths, so they are wider than they need to be.
*Source: `reports/evaluation.json` (forecast).*

**9. How many losing offers do you catch?**
Of 169 losing blanket offers given a control group, 70% are warned about or paused within four
weeks, while only 2% of profitable ones are ever paused. TrueLift's own 10 losing offers lose
₹444 a week between them, and none is flagged in four weeks.
*Source: `reports/evaluation.json` (detection).*

**10. Is the weekly check a peeking problem?**
It was. A pause now needs the offer's own control group to cross an always-valid boundary.
Placebo offers that change nothing are paused 1.8% of the time over four weekly looks and 2.2%
over twelve; the old rule paused 18.4% and 32.0%.
*Source: `reports/evaluation.json` (aa_test).*

**11. Why a T-learner?**
On five simulated markets it captures 78% of the best possible profit when targeting its top 30%,
against 70% for ranking by who is likely to order anyway. On real data the answer varies by
dataset, so the shadow phase inside Zomato would choose the learner.
*Source: `reports/learner_benchmark.json`, `reports/uplift_validation_*.json`.*

**12. Customers choose between restaurants. Doesn't that break your assumptions?**
Partly, and it is measured. If 10% of restaurants adopt TrueLift, they gain ₹95,839 a week and
the others lose ₹22,374, because some extra orders come from rivals. A pilot should randomise whole
localities as a check; the blueprint sizes that.
*Source: `reports/evaluation.json` (partial_adoption); `docs/integration_blueprint.md`.*

**13. Most of your control data is not randomised.**
In the shadow phase, offers, audiences and time slots are randomised, so being shown is random
given the features. Trained on held-out customers only, the model still ranks almost as well: Qini
0.218 against 0.229. On real logs we would use holdouts only.
*Source: `reports/evaluation.json` (control_set, uplift_quality).*

**14. Why can't the model pick the discount size?**
It could earn more (own-offer profit ₹9.57 lakh against ₹7.89 lakh), but losing offers rise from
10 to 28, because picking the best of noisy forecasts flatters them. A randomised size test picks
the better size 65% of the time in four weeks. The owner keeps the size.
*Source: `reports/exp_depth_choice.json`, `reports/exp_depth_test.json`.*

**15. How wide are the ranges for a small restaurant?**
Wide, and we say so. With 1,000 menu visits a week and a 10% holdout, one week of the restaurant's
own data gives ±5.4 points on a 3-point effect (an order rate rising from 7% to 10%). The estimate
leans on the model early and on the restaurant's own data later, and the approval screen states the
smallest effect four weeks can confirm.
*Source: `docs/method_and_evidence.md` (precision table).*

## Engineering

**16. Latency on the menu path?**
A dictionary lookup and a hash: 2.5 ms at the 95th percentile over HTTP, 0.27 ms inside the
service, and 524 decisions a second with eight callers on a laptop. No model runs while a
customer waits; decision tables are built at approval.
*Source: `reports/latency.json` (`scripts/bench_latency.py`).*

**17. What if your service is down or scoring fails?**
If scoring fails when a decision table is built, the table falls back to the owner's own rule
(everyone eligible sees the offer), each decision is flagged as degraded, and a counter in
`/metrics` must stay at zero. The control-group hash still applies, so measurement continues.
*Source: `docs/architecture.md`; `test_decision_table_falls_back_to_the_owners_rule_and_says_so`.*

**18. How do you know serving and analysis use the same control group?**
One function hashes (customer, offer) for both, and a test checks that the customers measured as
held out are exactly those served as held out. Each offer also gets a weekly sample-ratio check:
in the placebo test it raised 4 alarms in 2,736 weekly checks over twelve weeks (0 in the first four).
*Source: `truelift/assignment.py`; `test_serve_and_measurement_share_holdout`; `reports/evaluation.json` (aa_test).*

**19. What did your own testing find?**
50 findings, all fixed: a race between concurrent quotes, a simulator bug that made Zomato's
co-funding look far more expensive, serving and measurement holding out different customers, and
offers paused on noise. Each fix is listed with the test that guards it.
*Source: `docs/what_we_tested.md`, `DEVLOG.md` (corrections).*

**20. How does the model stay current?**
Every measured offer adds randomised data. A candidate model is promoted only if it ranks the next
held-out weeks better; in our retraining test it was (Qini 0.231 against 0.229), so it would be
promoted.
*Source: `reports/exp_retrain_loop.json`.*

## Domain and product

**21. Is commission charged before or after the discount?**
We do not know, so we ran both. At ₹60 off a ₹400 order the offer breaks even at 32 extra orders in
100 if commission is on the discounted bill, 45 if on the full bill. In the second case 50 of 300
blanket offers pay; TrueLift still finds 109 that do.
*Source: `truelift/economics.py`; `reports/evaluation.json` (pre_discount_commission).*

**22. Most offers are "40% off up to ₹80". You only do flat discounts.**
Percentage offers with a cap are supported end to end. The model scores them at their average
discount per use. With 15% off up to twice the flat amount, 146 of 300 blanket offers pay and 223
TrueLift offers do.
*Source: `reports/evaluation.json` (percentage_offers); `docs/decisions/0009-percentage-offers-at-their-average-discount.md`.*

**23. Where does the food cost come from?**
A default of 37% of the menu price; the Money page switches between 30%, 37% and 45%. The sweep
shows one claim that fails at 45%: TrueLift's commission lead over blanket offers. Inside Zomato
the owner would enter their own figure once.
*Source: `truelift/economics.py`, `reports/sensitivity.json`.*

**24. What about a new restaurant with no history?**
The model learned from all restaurants gives a first forecast with a wide range, and the approval
screen says how large an effect four weeks can confirm. We also tested holding out 30% for the first
two weeks while the range includes zero: it flags 74% of losing blanket offers within four weeks
against 70%, so the restaurant's own evidence builds faster.
*Source: `reports/evaluation.json` (detection, adaptive rule).*

**25. Will owners understand a range?**
Not yet measured: one interview so far (17 November, the manager of a chain outlet in
Gandhinagar), and its note is not written up yet. The page shows both a range and a chance ("8 in 10 chance it makes
you money"), and the field kit tests which one owners read correctly. We publish no finding we
have not collected.
*Source: `docs/field_research.md`, `docs/field_research/comprehension_cards.md`.*

## Fairness and regulation

**26. Is this personalised pricing?**
No one pays more than the menu price; held-out customers simply see no discount. The model reads
only order and visit history, the listing, the time and the offer, and a test fails if it reads
location, device, payment method or anything standing in for income.
*Source: `tests/test_fairness.py`, `docs/privacy_and_fairness.md`.*

**27. Regulars get fewer discounts. Is that fair?**
Under targeting, regulars are offered a saving on 7% of visits against 55% for others, because
they order anyway. Giving regulars a Brand Pack reward raises that to 78% at no cost to
own-offer profit (+₹7.89 lakh either way).
*Source: `reports/evaluation.json` (fairness).*

**28. Data protection?**
Zomato's own data, used inside Zomato for a stated purpose. Owners see results, never customers:
no order counts are shown for a group of fewer than 20 customers. Our reading of the 2025 rules is
in the privacy document, marked as our reading.
*Source: `docs/privacy_and_fairness.md`; `truelift/demo.py` (MIN_GROUP_CUSTOMERS).*

## Challenge

**29. Don't we already do this?**
"You may, for your own spend; we would like to know. DoorDash measures what ads add with ghost-ads
holdouts. What we have not seen is the result of a restaurant-funded offer shown to the owner at
the point of consent, and tied to renewal."
*Source: `docs/method_and_evidence.md` §11 (comparable work).*

**30. What is the weakest part?**
Every rupee is simulated. Within that, a suggested version's stated advantage is about five times
its true one (though 79% truly beat the owner's), and the four-week estimate over-states the truth
by ₹452 an offer. A shadow holdout on real offers fixes the first; more data per restaurant, the
rest.
*Source: `reports/evaluation.json` (selection), `reports/exp_holdout_draws.json`.*
