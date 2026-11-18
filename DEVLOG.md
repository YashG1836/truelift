# TrueLift: development log

How the Round 2 build went, including what did not work and what we changed because of it.
Results and method are in `docs/method_and_evidence.md`; this file is the trail behind them.

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

**12. Made it easy to present and to use alone.** The site was redesigned in the style of Zomato's
partner app and gained a guided demo (10 steps with captions, keyboard controls), a How it works
page (the problem as a picture, the four steps, a glossary, common questions), clearer weekly
results (whole orders, "this week" vs "so far", a chart of the estimate against the truth) and a
one-line summary of who sees the discount. A browser script runs the guided demo, every tab and a
manual flow, and fails on any error or broken number.

## Round 2, audit and rebuild (14–15 November 2026)

**13. We audited our own submission.** Every source file was read against the claims made about it:
50 findings, from a race between concurrent quotes to documents that disagreed with the code. All
were fixed, most with a test that fails if the fault returns; the list, with the guard for each, is
in `docs/what_we_tested.md` and `CHANGELOG.md`. The fixes changed the numbers, so all of them landed
before one final run, and the corrections below say what moved.

**14. The service became something Zomato could call.** Typed hooks under `/api/v1` with a contract
(`docs/openapi.json`), per-visitor sessions, OTP expiry and attempt limits, a hash-chained consent
ledger, and an exposure log that the weekly measurement reads, as it would read Zomato's own logs.
A customer's menu now reads a decision table built at approval, so no model runs on the customer's
path.

**15. Serving and measurement held out different customers.** The page's "control group" and the
measurement used two different random draws (TL-004). One hashed assignment is now shared by every
code path, and a test checks that the customers measured as held out are exactly those served as
held out.

**16. Forecasts were too low, for three reasons.** The quote read features computed after the
visits it was forecasting, so its customers looked more loyal than future visitors (TL-006);
training and serving computed the look-back windows differently (TL-007); and the shadow phase
explored discount sizes of ₹40 to ₹100 while owners' offers are 10% to 25% of their order, which
tree models cannot extrapolate to. With point-in-time features, one feature definition and a
shadow phase that explores the create screen's own options, the forecasts moved much closer to the
truth (the method document reports the check), and a skew and drift check now fails the pipeline
if the windows ever diverge.

**17. Placebo offers were being paused.** An A/A test (offers that change nothing) showed the old rule
pausing many of them, because a small control group's sample variance collapses (TL-009, TL-017).
A pause now needs the offer's own control group to show a loss beyond an always-valid boundary,
and the noise of each estimate is re-estimated every week across all running offers.

**18. The best of 34 forecasts flatters itself.** The suggested version's stated advantage ran far
above its true advantage (TL-018). Forecast gains are now calibrated on the shadow phase's holdouts,
a version is suggested only with at least a 60% chance of making money, and every suggestion shows
its range. The inflation is smaller but still large, and the documents and the page say so.

**19. More of what Zomato would ask.** The Brand Pack reward got its own control group. The pipeline
now reports whose orders the extra orders are, owners declining OTPs, a measure-only policy, Zomato
co-funding, partial adoption, five market seeds, fairness by segment with three priced mitigations,
eight assumptions swept, a learner benchmark and six experiments.

**20. On real data the shortcut is a real competitor.** Re-running the real-data check with the
baseline practitioners use (rank people by how likely they are to act at all) and intervals: on
Criteo's visits it does as well as every uplift model, and on rare purchases better; on Hillstrom's
women's e-mail the uplift models win in every split. We report both.

**21. The product grew to match.** Percentage-off-with-cap offers, renewal on measured evidence, a
"what if you had run your version" card, the weekly result's evidence and a privacy rule for small
groups, draft owner texts in Hindi, Kannada and Gujarati (off until reviewed), a Zomato-style
interface, an Operations tab, an offline bundle, and a claims ledger that fails the build when a
document's number drifts from `reports/`.

## Corrections

Statements we made earlier (in this log or the Round 2 write-up, tag `round2-submission`) that the
audit and the final run changed. Current values are checked against `reports/` by
`scripts/check_claims.py`.

| We said | Now | Why it changed |
|---|---|---|
| "Past offers vary the size only between restaurants" (step 6) | The shadow phase varies the size between restaurant-weeks, never between customers of one restaurant in one week | The old wording did not match the simulator (audit TL-027) |
| Letting the model choose the size lowered profit (step 6) | It raises own-offer profit (₹9.57 lakh against ₹7.89 lakh) and market-wide profit a little, but losing offers rise from 10 to 28; the owner still keeps the size | The shadow phase now explores the sizes owners use |
| TrueLift: 242 of 300 offers pay; the rule 211 (step 6) | 218 of 228 TrueLift offers pay (no offer is advised at the other restaurants); the rule 214 of 300 | Fixes to forecasts, selection and the no-offer rule |
| Top-up value learned as 0.60 (truth 0.50) (step 5) | 0.50 | Fitted on menu visits instead of orders (TL-020) |
| Subtracting the predicted outcome cut noise by 27% (step 7) | 6% on the full market | Measured over ten holdout draws of all offers (`reports/exp_variance_reduction.json`) |
| 80% ranges held the truth 67% of the time in week 1, 79–81% later (step 7) | 79% after one week, 87% after two, 90% after four | Weekly recalibration of both noise sizes |
| "Keep" verdicts right 87–92% (step 7) | 140 of 142 after one week, 111 of 111 after four | The same, plus pauses only on the offer's own evidence |
| The apparent bias was one random draw; ten draws averaged zero (step 7) | Across ten draws on the full market the four-week estimate over-states the truth by ₹452 an offer (standard error ₹89) | A real bias inherited from the model's forecast; disclosed |
| Zomato co-funding cost about ₹5 lakh a week for about 70 extra orders (step 8) | ₹57,527 a week and no extra order: a transfer to restaurants | A simulator bug paid co-funding on every redemption (TL-003) |
| On Criteo the model's top 30% held 84% of the extra visits (Qini 0.34) (step 9) | 84% still, but ranking by likely visitors also finds 84%; on purchases 72% against 92% for that ranking. Qini as scikit-uplift defines it: 0.078 | Baselines and the standard Qini were added (TL-039, TL-040) |
| Brand Pack chosen at 3 restaurants | 1 | Selection now needs a 60% chance of making money |

## Reproduce

```bash
uv sync                          # pinned environment from uv.lock
python tasks.py pipeline         # about 15 minutes on 8 cores; writes reports/ and the model
python tasks.py sensitivity      # eight assumptions low and high
python tasks.py benchmark        # uplift learners against the truth
python tasks.py experiments      # oracle, size choice, noise, holdout draws, retraining, size test
python tasks.py realdata         # Criteo and Hillstrom, downloaded and checksummed
python tasks.py test --all       # every test, including the golden numbers
python tasks.py serve            # the full service and page at http://localhost:8000
```

## Next

1. Interview 6–8 restaurant owners with the field kit (`docs/field_research.md`). The first, with
   the manager of a chain outlet in Gandhinagar, took place on 17 November 2026; its note is still
   to be written up.
2. Ask Eternal whether commission is charged before or after the discount (break-even 32% against 45%
   at 15% off) and whether anonymised offer logs or a shadow holdout are possible.
3. A shadow holdout on real offers in one city, then the randomised pilot sized in
   `docs/integration_blueprint.md`.
