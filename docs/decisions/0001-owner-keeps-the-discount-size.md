# 0001 The owner keeps the discount size

**Decision.** TrueLift never changes the size of the discount the owner chose. It compares about 34
versions of the same discount (who sees it, minimum order, time of day, Brand Pack) and suggests the
best, or no offer when none is likely to make money.

**Why.** Past offers vary the size only between restaurant-weeks, never between customers of the
same restaurant in the same week, so a model learns little about how the same customers respond to a
bigger or smaller discount. Letting the model choose the size raises restaurants' profit from their
own offers a lot but their profit across the market only a little, because deeper discounts mostly
win orders from other restaurants, and it nearly triples the offers that lose money
(`reports/exp_depth_choice.json`). The size is also the owner's commercial decision.

**What follows.** A size change should come from a test that gives customers one size or another at
random. `scripts/experiments.py depth-test` runs one in the simulator: four weeks of a single
restaurant's own data pick the truly better size about two times in three, and only half the time
for the smaller restaurants (`reports/exp_depth_test.json`), so such tests need pooling across
similar restaurants or longer runs.
