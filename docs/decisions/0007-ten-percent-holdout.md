# 0007 One customer in ten is held out

**Decision.** A random 10% of the customers who could get an offer do not see it, by the hash of
decision 0002. Weeks one and two may hold out more when the forecast's range includes zero
(adaptive holdout, evaluated in the pipeline).

**Why.** The holdout is what makes the measurement possible, and it has a price: the held-out
customers' extra orders are given up. Ten per cent keeps that price small (reported as the control
group's cost on the Evidence page) while giving the fleet recalibration and larger restaurants
enough held-out orders within four weeks.

**What follows.** Held-out customers pay normal menu prices; no one is charged more. The share is a
setting (`TRUELIFT_HOLDOUT`), and the quote states the smallest weekly effect four weeks of that
control group can confirm.
