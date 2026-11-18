# 0009 Percentage offers are scored at their average discount per use

**Decision.** A percentage offer ("30% off up to Rs 60") is scored by the model as a flat offer of
its average discount per order that uses it, computed from the restaurant's usual order values. The
simulator gives each customer their own bill's discount, min(percentage x bill, cap), and the money
of every order uses that discount. TrueLift's versions keep the owner's percentage and cap.

**Why.** The shadow phase explored flat discounts only, so the model has never seen a percentage
offer. Its response depends on the rupees saved, and the average saving is the natural single
number. The forecast check measures what this costs, for the usual pairing (the cap reached from half
the usual order up) and for a proportional offer where the discount follows every bill
(`percentage_offers` in `reports/evaluation.json`).

**What follows.** The Money page shows how a percentage offer's real discount, and the share of extra
orders it needs, change with the order's size. Exploring percentage offers in the shadow phase would
let the model learn them directly.
