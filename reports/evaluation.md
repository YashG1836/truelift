# Evaluation summary

Every table below is written from the JSON reports in this folder by `scripts/render_tables.py`
(`--check` fails when a table no longer matches its report). Customers, orders and profits are
simulated; restaurant listings are real public 2019 data. Per week, 300 restaurants.

## The three policies

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

## Spread over five market seeds

<!-- BEGIN:seeds-table -->
| Mean ± sd over 5 market seeds | Today: same discount for everyone | Rule: new customers only | TrueLift |
|---|---|---|---|
| Offers that pay for themselves | 132 ± 4 | 210 ± 4 | 223 ± 8 |
| Restaurants' profit from their own offers | +₹6.90 lakh ± 0.06 | +₹7.20 lakh ± 0.04 | +₹7.84 lakh ± 0.07 |
| Restaurant profit vs no offers (market) | +₹2.39 lakh ± 0.06 | +₹3.81 lakh ± 0.03 | +₹4.78 lakh ± 0.08 |
| Zomato commission vs no offers | +₹6.43 lakh ± 0.03 | +₹5.84 lakh ± 0.04 | +₹6.55 lakh ± 0.02 |
| Discount given | ₹16.84 lakh ± 0.08 | ₹10.83 lakh ± 0.08 | ₹10.79 lakh ± 0.18 |
<!-- END:seeds-table -->

## Other market assumptions

<!-- BEGIN:scenario-table -->
| Scenario | Offers that pay: today / rule / TrueLift | Own-offer profit: today / rule / TrueLift | Restaurant profit vs no offers: today / rule / TrueLift | Zomato commission vs no offers: today / rule / TrueLift |
|---|---|---|---|---|
| Customers 30% less price-sensitive | 70 / 130 / 153 | ₹2.16 lakh / ₹3.39 lakh / ₹3.96 lakh | −₹1.06 lakh / +₹1.00 lakh / +₹2.23 lakh | +₹3.30 lakh / +₹3.24 lakh / +₹3.71 lakh |
| Base case | 130 / 214 / 218 | ₹6.94 lakh / ₹7.16 lakh / ₹7.89 lakh | +₹2.46 lakh / +₹3.80 lakh / +₹4.77 lakh | +₹6.45 lakh / +₹5.79 lakh / +₹6.53 lakh |
| Customers 30% more price-sensitive | 181 / 245 / 252 | ₹11.62 lakh / ₹10.95 lakh / ₹11.94 lakh | +₹6.03 lakh / +₹6.72 lakh / +₹7.67 lakh | +₹9.64 lakh / +₹8.47 lakh / +₹9.46 lakh |
| Commission on the price before the discount | 50 / 112 / 109 | ₹2.01 lakh / ₹4.00 lakh / ₹5.12 lakh | −₹2.47 lakh / +₹0.64 lakh / +₹2.77 lakh | +₹10.63 lakh / +₹8.47 lakh / +₹8.58 lakh |
<!-- END:scenario-table -->

## Weekly measurement of TrueLift's offers

<!-- BEGIN:measurement-table -->
| After | Truth inside the 80% range | Average error: control group only | Model only | TrueLift combined | "Keep" verdicts truly positive |
|---|---|---|---|---|---|
| 1 week | 79% | ₹1,975 | ₹655 | ₹642 | 140 of 142 |
| 2 weeks | 87% | ₹2,892 | ₹1,220 | ₹1,166 | 113 of 114 |
| 4 weeks | 90% | ₹4,160 | ₹2,212 | ₹2,054 | 111 of 111 |
<!-- END:measurement-table -->

## Who gets discounts

<!-- BEGIN:fairness-table -->
| Policy | Regulars offered a saving | Others offered a saving | Loyalty gap (points) | Restaurants' profit from their own offers | Offers that pay |
|---|---|---|---|---|---|
| Today: same discount for everyone | 100% | 100% | 0 | +₹6.94 lakh | 130 |
| TrueLift | 7% | 55% | 48 | +₹7.89 lakh | 218 |
| TrueLift + Brand Pack reward for regulars | 78% | 55% | −24 | +₹7.89 lakh | 218 |
| TrueLift, regulars always eligible | 78% | 55% | −23 | +₹6.98 lakh | 163 |
| TrueLift + a random 20% of others shown | 21% | 59% | 38 | +₹7.65 lakh | 198 |
<!-- END:fairness-table -->

## Percentage offers

<!-- BEGIN:pct-table -->
| Format | Rupees off per use, share of the flat amount | Offers that pay: blanket / TrueLift | Own-offer profit: blanket / TrueLift | Restaurant profit vs no offers (market): blanket / TrueLift | TrueLift forecast against truth |
|---|---|---|---|---|---|
| Flat amount (as above) | 100% | 130 / 218 | +₹6.94 lakh / +₹7.89 lakh | +₹2.46 lakh / +₹4.77 lakh | 0.82 |
| Percentage up to the flat amount (cap reached from half the usual order) | 100% | 130 / 218 | +₹6.94 lakh / +₹7.89 lakh | +₹2.46 lakh / +₹4.77 lakh | 0.82 |
| 15% off up to twice the flat amount (discount follows the bill) | 105% | 146 / 223 | +₹8.15 lakh / +₹7.90 lakh | +₹3.46 lakh / +₹5.11 lakh | 1.07 |
<!-- END:pct-table -->

## Real randomised data (advertising and e-mail, not food)

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

The method, the meaning of each row and the limits are in `docs/method_and_evidence.md`.
