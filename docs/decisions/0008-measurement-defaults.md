# 0008 How the weekly measurement computes its noise

**Decision.** The weekly estimate compares customers, not visits (a customer's visits are alike),
subtracts each visit's predicted no-offer outcome (regression adjustment), and takes its noise from
the model's expected variance scaled by a factor learned from split halves, not from the small
control group's own sample variance.

**Why.** Candidate variants were compared against the truth in the simulator: the rule was to keep
the one whose 80% ranges hold the truth closest to 80% of the time after weeks one, two and four,
for profit and orders (`measurement_variants` in `reports/evaluation.json`). A control group of a
few dozen visits has a handful of orders; its sample variance is erratic and is zero when it has no
order, which made placebo offers look certain.

**What follows.** The variant in use and the closest-to-nominal one are both reported, so a change
in the data that favours another variant is visible.
