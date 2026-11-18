# 0006 Two gradient-boosted models (a T-learner), checked against other learners

**Decision.** The uplift model is a T-learner: one gradient-boosted classifier for ordering without
an offer, one for ordering with it, with known directions enforced (a bigger discount never lowers
the chance of ordering).

**Why.** It is simple to explain and to check, it needs only order history, and in the simulator it
ranks customers as well as the S-, X- and doubly robust learners (`reports/learner_benchmark.json`).

**What we found on real data.** On Criteo's advertising tests, ranking people by how likely they are
to act at all does as well as every uplift model on visits, and better on rare purchases, where the
X-learner is the strongest uplift model. On Hillstrom's women's e-mail the uplift models beat that
shortcut (`reports/uplift_validation_*.json`). The right ranking depends on the setting.

**What follows.** Inside Zomato the shadow phase's random holdout scores every candidate ranking
(T-, X-learner, the shortcut) on Zomato's own offers before any is used. Switching to an X-learner is
the first candidate change to test there.
