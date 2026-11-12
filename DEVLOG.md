# TrueLift: development log

How the Round 2 build went, including what did not work and what we changed because of it.
Results and method are in `TrueLift_Round2_Plan.md`; this file is the trail behind them.

## Round 1 (October 2026)

Problem statement: restaurant discounts are judged by the orders that use them, not the orders
they create. Since August 2026 restaurant-funded offers on Zomato need the owner's OTP approval, so
an owner who cannot see whether an offer pays will stop approving it. Submitted as a one-page PDF
(`docs/round1_problem_statement.pdf`).

## Round 2 (12–13 November 2026)

**1. Re-checked the facts.** Eternal's Q2 FY27 letter (food delivery margin 5.5% of order value;
advertising and promotion spend up 41% year on year), the August consent agreement, Swiggy's
discount self-serve tool and Zomato's Brand Packs. Existing tools target segments and report
redemptions; none measure what an offer caused. Sources are in the plan, §1.

**2. Exact money maths.** One module computes every rupee figure. With commission plus GST at the
exact 29.5% (Round 1 rounded to 30%), the Round 1 example becomes −₹210 a week for a blanket offer
and +₹2,101 with targeting.

**3. A market where the truth is known.** No public dataset has restaurant offers with rupee
outcomes and a control group, so we built a simulated Bengaluru: 300 real Zomato listings and
30,000 synthetic customers of four hidden types. Because the simulator knows each customer's chance
of ordering with and without every discount, every estimate can be checked. Calibrated so that
average order value is ₹460 and 34% of orders using a blanket ₹60 offer are truly extra.

**4. Uplift model.** A two-model approach (chance of ordering with and without the offer) on
gradient-boosted trees. Against the simulator's truth, its predicted uplift tracks the true uplift
decile by decile; Qini 0.24 against 0.01 for random. Targeting "new customers first", the usual
segment rule, scored below random.

**5. First full comparison failed.** TrueLift made less profit than the simple "new customers only"
rule (₹6.46 lakh vs ₹7.34 lakh a week). A test with one fixed discount showed targeting itself was
fine (it beat the rule by 15%), so we looked elsewhere and found two errors:
- the usual order value was estimated from orders that included customers who skipped a
  minimum-order offer, which biased it low;
- the engine assumed everyone shown a minimum-order offer uses it. Past offers said 38% to 100% do,
  depending on how high the minimum is. We now learn how much customers value a top-up from past
  offers (learned 0.60; the simulator's hidden value is 0.50).

**6. The model should not pick the discount size.** Even after the fixes, letting the model choose
between ₹40, ₹60 and ₹80 lowered profit: past offers vary the size only between restaurants, and
picking the best of many uncertain forecasts favours the over-estimated ones. Decision: the owner
keeps the discount size; TrueLift decides who sees it, the minimum order, the time slot and the
Brand Pack. With that, TrueLift beat both baselines (242 of 300 offers pay, vs 130 blanket and 211
for the rule). A randomised depth test is the right way to change sizes later.

**7. Measuring small restaurants.** A 10% control group alone cannot measure a restaurant with
~50 orders a week (±5.4 points on a 3-point effect in one week), so the weekly estimate combines
the restaurant's own control group with the model, weighted by precision. An apparent bias in the
demo turned out to be one random draw reused across runs; tests over 10 draws averaged zero.
Subtracting each visit's predicted no-offer outcome before comparing groups cut noise by 27%.
Result: 80% ranges cover the truth 67% of the time after one week and 79–81% from week two;
"keep" verdicts are right 87–92% of the time.

**8. Zomato co-funding needs measurement too.** Paying half the discount for customers new to
Zomato, without measuring Zomato's own gain, cost about ₹5 lakh a week for about 70 extra orders.
We present it as a caution, not a feature.

**9. Real data.** Meituan's MT-LIFT coupon dataset was the plan, but its download links are broken
(open issues on its GitHub page) and one issue reports imbalanced groups. We used Criteo's open
uplift data instead (14 million users, random 15% held out of ads): on 4.2 million unseen users the
model's top 30% held 84% of all the extra visits (Qini 0.34 vs 0.005 random).

**10. Demo checks.** The prototype was driven end to end in a browser on desktop and phone. Across
five demo offers, the true value fell inside TrueLift's 80% range in 15 of 20 weeks: Burger King 8 of
8 (two offers), Domino's 4 of 4, On The Nose 3 of 4, Empire Restaurant 0 of 4 (estimate high,
"keep" verdict still right). That matches the ~80% coverage measured across all 300 restaurants.

**11. Data labelling.** Restaurant names and listing details are real public listings; their
customers, orders and profits are simulated, and every screen says so.

## Reproduce

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/run_pipeline.py          # about 6 minutes; writes reports/
.venv/bin/python scripts/validate_uplift.py criteo  # about 30 seconds after the 300 MB download
.venv/bin/python -m pytest -q                     # 11 tests
.venv/bin/uvicorn truelift.api:app --port 8000    # the full service and UI
```

## Next

1. Interview 6–8 restaurant owners on Zomato: offer reports, the OTP screen, payout statements.
2. Ask Eternal whether commission is charged before or after the discount (break-even 32% vs 45%
   at 15% off) and whether anonymised offer logs or a shadow test are possible.
3. Build the randomised depth test and a control group for Zomato's own discount spend.
