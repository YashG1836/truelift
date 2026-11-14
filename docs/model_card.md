# Model card: TrueLift uplift model

**What it predicts.** For one customer opening one restaurant's menu, the chance of ordering from that
restaurant without an offer and with a given offer. The difference (the uplift) decides who sees a
discount and adds up to the forecast an owner sees before approving.

**How.** Two gradient-boosted classifiers (scikit-learn `HistGradientBoostingClassifier`): one learns
ordering without an offer from visits that saw none; the other learns ordering with an offer from
visits that saw one, with the offer's size and minimum order as inputs. Known directions are
enforced: a bigger discount or Brand Pack reward never lowers the chance of ordering; a higher
minimum order never raises it. Code: `truelift/model.py`; training: `truelift/training.py`.

**Inputs.** Only order and visit history on Zomato, the restaurant's public listing, the time of the
visit and the offer itself. The full list, each input with its meaning, is `ALLOWED_FEATURES` in
`truelift/model.py`; `tests/test_fairness.py` fails if the model reads anything else or if an input's
name refers to a protected trait or to where a customer lives. Never location, device, payment method
or anything that stands in for income.

**Training data.** Simulated. Twelve weeks of a simulated Bengaluru market (300 real public 2019
restaurant listings, 30,000 synthetic customers of four hidden types): eight weeks of today's offers
followed by four weeks of TrueLift's shadow phase, which varies the designs owners already run at
random (sizes from the create screen, minimum orders, time slots, audiences, Brand Pack) and holds
out a random 10% of eligible customers. About one million menu visits. No real customer data is
used anywhere.

**How it is checked.** Against the simulator's truth (it knows every visit's chance of ordering with
and without each offer): correlation with the true uplift, Qini, the profit of targeting its top 30%,
reliability by decile, and the forecast an owner approves against the true effect in the market it
was made for. Against other learners (`reports/learner_benchmark.json`, five markets). On real
randomised data: Criteo's open ad-holdout benchmark (`reports/uplift_validation_criteo.json`). The
numbers are in `reports/` and on the Evidence page; they are not repeated here so they cannot drift.

**Calibration.** Forecast gains are scaled by factors learned from the shadow phase's random holdouts
(cross-fitted, above and below zero). The weekly measurement's two noise sizes are re-estimated every
week across the running offers (split halves for the control groups' noise; spread of own against model
estimates for the model's error). The model bundle records its version, training rows, library
versions, inputs and these calibration factors, and loads only if its SHA-256 checksum matches and
it was built on the inputs this code uses.

**Intended use.** Ranking customers for a restaurant-funded offer the owner has already chosen, and
giving the owner a forecast with an honest range before they approve. Not for setting prices, not for
choosing the discount size (that stays the owner's call; a randomised test of sizes is the right
tool, `scripts/experiments.py depth-test`), and not for any decision about a customer beyond whether
they see an offer.

**Known limits.**
- Everything is simulated except the Criteo check, which is advertising, not food discounts.
- Predicted uplift is too spread out: the top decile is over-predicted by about a quarter (slope of
  truth on prediction about 0.75), so forecasts are scaled and ranges are shown.
- The stated advantage of a suggested version over the owner's runs higher than its true advantage,
  because the best of about 34 forecasts favours the ones that came out high; most suggestions still
  truly beat the owner's offer.
- Regulars are offered fewer discounts, because they order anyway; the fairness report and the Brand
  Pack mitigation are on the Evidence page.
- The sensitivity sweep (`reports/sensitivity.json`) lists where the claims stop holding, in words.
