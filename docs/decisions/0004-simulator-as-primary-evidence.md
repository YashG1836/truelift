# 0004 A simulated market with a known truth is the main evidence

**Decision.** The main evidence is a simulated Bengaluru market: 300 real public 2019 listings and
synthetic customers whose response to every offer is known. Real data is used where it exists
(Criteo's advertising tests, Hillstrom's e-mail test) to check the method, not Zomato's numbers.

**Why.** No public dataset has restaurant offers with rupee outcomes and a random control group.
Only a market where the truth is known can show whether a forecast, a range or a verdict is right,
which is the question that matters. The simulator's assumptions are listed with what would replace
each inside Zomato (`docs/simulator_datasheet.md`), and the sensitivity sweep shows where each claim
stops holding (`reports/sensitivity.json`).

**What follows.** Every screen and document says the outcomes are simulated. The first phase inside
Zomato (integration blueprint) replaces the simulator with a shadow holdout on real offers.
