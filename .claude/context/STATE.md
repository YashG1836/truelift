# Current state

Last updated: 15 Nov 2026 by Kshitish (Claude), freeze of branch `kshitish`. Overwrite lines that become wrong;
do not append history here (history goes in SESSIONS.md).

## Status
- Round 2 submission is live from `main` (tag `round2-submission`). Branch `kshitish` holds the audited rebuild
  (service v1, measurement, market analyses, real-data checks, restyle, docs); not merged into `main` yet.
- Branches: `main` (shared), `kshitish` (Kshitish's work, CI publishes the demo from it on `[deploy]`), `gh-pages`
  (generated demo site, do not edit).
- Numbers are frozen on `kshitish` (one final run, 14 Nov night): `reports/` and the committed model
  `data/processed/model.pkl` (+ `.sha256`). Any later change that moves a number needs a new full run and must
  update README, DEVLOG, docs and this file together; `scripts/check_claims.py` and `render_tables.py --check` fail
  until they agree.
- Teammates ksawesome (Kshitish) and BhavayGoyal have write access. History rewrite of 13 Nov is done (never merge
  old history back).

## Headline numbers (generated from `reports/evaluation.json`; per week, 300 simulated restaurants)
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

- Measurement (TrueLift offers): truth inside the 80% range 79% / 87% / 90% after weeks 1 / 2 / 4; "keep" verdicts
  truly positive 140 of 142 / 113 of 114 / 111 of 111; placebo offers paused 1.8% over four weekly looks.
- Selection: the suggested version truly beats the owner's at 79% of restaurants, but its stated advantage is about
  five times its true one (disclosed on the page and in the docs).
- Real data (`reports/uplift_validation_*.json`): Criteo visits, every ranking incl. "likely to act anyway" finds
  83-85% in the top 30%; purchases T-learner 72% vs the shortcut 92%; Hillstrom women's e-mail, uplift models beat
  the shortcut in 5 of 5 splits; dollars spent too noisy to rank.
- Money example (`truelift/economics.py`): ₹400 order keeps ₹134 at full price, ₹91.70 with ₹60 off; break-even
  21 / 32 / 42 / 53% of orders extra at 10-25% off (45% at 15% off if commission is on the pre-discount bill).

## Demo site
- 32 restaurants (tasks.py `DEMO_RESTAURANTS`, six localities x five price bands); 233 Burger King opens first.
  Flat and percentage designs (258 files a restaurant). Draft translations kept only for 233.
- Tabs: Demo (guided demo, 10 steps, Back and keys), How it works, Evidence, Money maths, Operations.
- Offline bundle: `python scripts/build_offline.py` after an export -> `dist/truelift-offline/`.

## Open tasks (owner in brackets; change when you pick one up)
1. [team] Interview 6-8 restaurant owners with the field kit (`docs/field_research.md`, `docs/field_research/`).
2. [team] Native-speaker review of `truelift/static/i18n/{hi,kn,gu}.json`, then switch `TRUELIFT_LANGUAGES=1` (D4).
3. [team] Send Eternal the questions in `docs/method_and_evidence.md` §10.
4. [team] Rehearse the 5-minute demo (`docs/method_and_evidence.md` §8, pitch folder) with the guided demo.
5. [Yash] Review the restyle of `truelift/static/` (his last area) before `kshitish` is merged into `main`.
6. [team] Merge `kshitish` into `main` (DECISIONS D13 supersedes D5 at merge); repository settings listed in the handoff.

## Known limits (say these if asked)
- All outcomes are simulated; only the real-data checks (ads, e-mail) are real, and neither is about restaurant offers.
- The suggested version's stated advantage runs well above its true advantage.
- Across ten holdout draws the four-week estimate over-states the truth by about ₹450 an offer (model prior bias).
- Small restaurants: a 10% holdout alone gives ±5.4 points in a week on a 3-point effect, so the estimate leans on
  the model early and on the restaurant's own holdout later.

## Who is on what (update when you start or finish; prevents two people editing the same file)
- Yash: idle since 13 Nov; to review the `truelift/static/` restyle on `kshitish`.
- Kshitish: branch `kshitish`. M1-M3 and the M4 documents and field kit done; finishing export, deploy, pitch
  (`docs/pitch/`) and M5 checks.
  Files: `truelift/*`, `scripts/*`, `tests/*`, `docs/*`, `.github/*`.
- Bhavay: not started in the repo yet. Add your area here.
