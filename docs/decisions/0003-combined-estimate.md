# 0003 The weekly result combines the offer's own control group with the model

**Decision.** Each week, the offer's own comparison (shown against held-out customers, adjusted by
each visit's predicted outcome) is combined with the model's forecast, each weighted by how precise
it is. The two noise sizes are re-estimated every week across all running offers: two random halves
of each offer's customers show the real noise of its own estimate, and the spread of own estimates
around the model's shows the model's real error. Pausing an offer needs the offer's own evidence
beyond an always-valid boundary; the model alone can never pause an offer.

**Why.** A restaurant with about fifty orders a week has a handful of held-out orders in a week:
alone, its control group is too noisy to say anything early. The model, learned from all
restaurants, is precise but can be wrong for one restaurant. Weighting by precision uses the model
early and the restaurant's own evidence more each week. The fleet recalibration needs no truth, so
it works in production as it does in the simulator.

**What follows.** The Evidence page reports the combined error against both parts alone, the share
of 80% ranges that hold the truth, placebo offers that must never pause, and how fast losing offers
are caught. An owner always sees the weight on their own control group ("Show me how you know").
