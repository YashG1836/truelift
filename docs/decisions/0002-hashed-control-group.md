# 0002 One hashed control group, shared by serving and measurement

**Decision.** Whether a customer is held out of an offer is a hash of (customer, offer) with a fixed
salt (`truelift/assignment.py`). Serving, the customer panel, the simulated weeks and the
measurement all call the same function. The Brand Pack reward and the depth test have their own
salts, so their control groups are independent of the offer's.

**Why.** The measurement is valid only if the customers it treats as held out are exactly the ones
who did not see the offer. Two code paths that each decide this were the cause of a real fault
(audit TL-004). A hash needs no stored state, gives the same answer on every request, keeps a
held-out customer held out for the offer's life, and can be recomputed by anyone auditing the result.

**What follows.** A renewal keeps the first offer's key, so the same customers stay held out and the
measurement carries on. The sample-ratio check in every weekly result would show a broken split.
The salt must never change within an offer (integration blueprint, failure table).
