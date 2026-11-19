# Current state

Last updated: 19 Nov 2026 by Yash (Claude): header on one line, simulated-data note moved to the page foot.
Overwrite lines that become wrong; do not append history here (history goes in SESSIONS.md).

## Status
- 18 Nov: `kshitish` merged into `main` (pull request #1, merge commit `02ff475a`; D13 replaces D5). `main` now
  holds the audited rebuild v2.0.0, the README and the first interview. Tag `round2-submission` still marks 13 Nov.
- **Submission folder `submission/`**: `SUBMISSION.md` (every link, a paste-ready description, how to present),
  `TrueLift_Report.pdf` (IEEE conference format, 7 pages), `TrueLift_Presentation.pdf` + `.html` (14 slides, Zomato
  style), `TrueLift_Demo.mp4` (copy of `docs/pitch/demo.mp4`). Rebuild: `python submission/src/build.py` (numbers
  from the claims ledger and generated tables; needs tectonic and Chrome). The README links each file.
- Branches: `main` (shared; CI publishes the demo from it on `[deploy]`), `kshitish` (Kshitish's work), `gh-pages`
  (generated demo site, do not edit).
- Public demo https://yashg1836.github.io/truelift/ (`build.json` names the commit it was built from): published
  19 Nov from `main@f6faf6f7` by CI (run 44465778254, every job green, browser tests on the public URL
  passed), 32 restaurants, opens on the Overview tab, header on one line. CI publishes from `main` on `[deploy]`.
- README images (`docs/img/`, `python tasks.py screenshots` after `python tasks.py export 233`): whole cards only,
  nothing cut at an edge; `owner_flow.png` is the owner's four screens two by two; the guided-demo GIF is taken at
  1440 x 1000 so every frame shows the whole phone. The report and slides use the same images.
- Release v2.0.0 https://github.com/YashG1836/truelift/releases/tag/v2.0.0: annotated tag on `8ac3ca4`, the commit
  the public demo is built from. Files: `truelift-offline.zip` (made from that deployed site; offline browser tests
  8 of 8), `TrueLift_deck.pdf`, `TrueLift_one_page.pdf`; SHA-256 in the notes. Tag `round2-submission` unchanged.
- Numbers are frozen on `kshitish` (one final run, 14 Nov night): `reports/` and the committed model
  `data/processed/model.pkl` (+ `.sha256`). Any later change that moves a number needs a new full run and must
  update README, DEVLOG, docs and this file together; `scripts/check_claims.py` and `render_tables.py --check` fail
  until they agree.
- Teammates ksawesome (Kshitish) and BhavayGoyal have write access.
- The 13 Nov history rewrite was **not** run: the commits of 12-13 Nov on `main` still carry a Claude co-author line
  (`git log origin/main --format=%B | grep -c anthropic` prints 10). Rewriting now would also move `v2.0.0`, its
  release and every hash the docs cite, so leave it unless the whole team decides otherwise. New commits carry no
  attribution (`.claude/settings.json`, hook).

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
- Tabs: Overview (opens first: what it is for, the problem, the solution, who gains, results, how we know, a map of
  the site; numbers from the evidence), Demo (guided demo, 10 steps, Back and keys; `#tab=demo`), How it works,
  Evidence, Money maths, Operations. Tests and scripts open `#tab=demo`. Header is one line on desktop (no tagline);
  the simulated-data note is the small page foot of every tab.
- Offline bundle: `python scripts/build_offline.py` after an export -> `dist/truelift-offline/`.
- Pitch in `docs/pitch/`: deck (PDF, PPTX, `deck.html`), speaker notes, runbook (choreography, failure drill,
  90-second audience script), 30-question bank (numbers in the claims ledger), one-pager with QR, `demo.mp4`.
  Rebuild with `python tasks.py deck` and `python tasks.py video` (after export); `tests/test_pitch.py` checks.

## Open tasks (owner in brackets; change when you pick one up)
1. [team] Interview 6-8 restaurant owners with the field kit (`docs/field_research.md`, `docs/field_research/`).
   One done 17 Nov (manager of a chain outlet, Gandhinagar; photos in `docs/field_research/photos/`, D17): write
   up its note from the template, fill the table, delete the raw photos.
2. [team] Native-speaker review of `truelift/static/i18n/{hi,kn,gu}.json`, then switch `TRUELIFT_LANGUAGES=1` (D4).
3. [team] Send Eternal the questions in `docs/method_and_evidence.md` §10.
4. [team] Rehearse with `docs/pitch/runbook.md` (three runs) and own ten questions each from `docs/pitch/questions.md`;
   present with the guided demo, slides in `submission/` as backup.
5. [Yash] Repository settings in `docs/handoff.md` 8-10 (branch protection for `main`, Pages source, security alerts).
6. [Bhavay] Commit his own work under his own name (handoff 4).

## Known limits (say these if asked)
- All outcomes are simulated; only the real-data checks (ads, e-mail) are real, and neither is about restaurant offers.
- One interview with a restaurant manager so far; no findings until its note is written up.
- The suggested version's stated advantage runs well above its true advantage.
- Across ten holdout draws the four-week estimate over-states the truth by about ₹450 an offer (model prior bias).
- Small restaurants: a 10% holdout alone gives ±5.4 points in a week on a 3-point effect, so the estimate leans on
  the model early and on the restaurant's own holdout later.

## Who is on what (update when you start or finish; prevents two people editing the same file)
- Yash: 18 Nov reviewed and merged pull request #1, rewrote `README.md`, made `submission/`, moved the deploy to
  `main` in `.github/workflows/ci.yml`. Files: `README.md`, `submission/*`.
- Kshitish: branch `kshitish` (merged into `main` 18 Nov; pull `main` before new work). M1-M5 done, release v2.0.0,
  interview record. Files: `truelift/*`, `scripts/*`, `tests/*`, `docs/*`, `.github/*`.
- Bhavay: not started in the repo yet. Add your area here.
