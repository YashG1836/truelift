# Session log (newest first)

Every Claude adds one entry at the top before its last commit of a session. Keep each entry under ~12 lines.
If two people add entries at once, keep both when resolving the merge.

Template:
```
## <date> · <person> (<model>) · branch <name>
- Did: what changed, in one or two lines each.
- Files: main paths touched.
- Checked: tests / ui_check / live site / not checked.
- Numbers changed: which, and where they now live (or "none").
- Next / open: what the next person should pick up.
```

## 18 Nov 2026 · Yash (Claude Opus) · branch main (merge, README, submission folder)
- Did: reviewed pull request #1 (CI green; locally lint 0 errors, 185 tests, 194 claims, tables, photos have no
  metadata and bystanders blurred) and merged it with a merge commit (`02ff475a`). Deploy moved to `main` (both
  branch names in `ci.yml`; changing only the deploy job, as handoff 6 said, would have published 2 restaurants).
  CodeQL's one alert (test_api CSP substring) fixed by comparing the policy's sources whole. README rewritten:
  shorter, "Start here" links to demo, report, slides, video, offline copy, `submission/`. New `submission/`:
  SUBMISSION.md, IEEE-format report (tectonic, IEEEtran), 14 Zomato-style slides (PDF + browser copy with arrow
  keys), demo video; built by `submission/src/build.py` from the claims ledger and generated tables. STATE said the
  13 Nov history rewrite was done; it was not, corrected.
- Files: README.md, submission/*, docs/claims.yml (+4 claims), .github/workflows/ci.yml, tests/test_api.py,
  docs/handoff.md, CLAUDE.md, .gitignore, .claude/context/*.
- Checked: claims 198 of 198, tables, lint (ruff, pyright 0), fast tests 170 passed; every report and slide page
  looked at; slides' browser navigation (no page errors). Not checked: the CI deploy run from `main` (started by
  this commit's `[deploy]`) and the public URL after it.
- Numbers changed: none.
- Next / open: confirm the deploy (`build.json` names the new commit); repository settings (handoff 8-10).

## 18 Nov 2026 · Kshitish (Claude Opus) · branch kshitish (README, screenshots, first interview)
- Did: README rewritten for judges: intro and links, the guided demo as `docs/img/tour.gif`, the 100-order problem
  picture, four phone screens, Zomato's side, results (seeds, weekly measurement and real-data tables generated, in
  `<details>`), the hooks diagram (mermaid), field research with two photos, a repository map. `tests/ui/screenshots.js`
  takes every image (`python tasks.py screenshots` = `make_video.py --no-video`, GIF via imageio-ffmpeg); old
  `docs/demo_*.png` removed. First owner interview recorded (17 Nov, manager of a chain outlet, Gandhinagar; no
  findings until the note is written): field_research.md, consent rule, method §7, handoff 2, DEVLOG Next, Q25, deck
  slide A6 (deck rebuilt), D17. How it works page: legend swatch blue, "218 of 228" (code only, not deployed).
- Files: README.md, docs/img/, docs/field_research*, docs/claims.yml (7 README claims), tests/ui/screenshots.js,
  scripts/make_video.py, scripts/make_deck.py, tasks.py, tests/test_pitch.py, truelift/static/app.js, docs/pitch/.
- Checked: claims 194 of 194, tables, fast tests 173 passed, lint (ruff, format, pyright 0 errors), Playwright
  static + phone 8 of 8 and `ui_check.js` (no problems) on `site/` refreshed with `export_static.py --assets`.
  Every image and both photos looked at. Not checked: the public URL (the fixes are not deployed).
- Numbers changed: none (the README's money example is now in the ledger).
- Next / open: the team merges the pull request `kshitish` -> `main` (merge commit); the next `[deploy]` publishes the
  How it works fixes; write up interview 1's note and delete the raw photos.

## 15 Nov 2026 · Kshitish (Claude Opus) · branch kshitish (release v2.0.0)
- Did: owner's go-ahead, so annotated tag `v2.0.0` on `8ac3ca4` (the deployed commit) and the GitHub release with
  the CHANGELOG 2.0.0 notes and three files: `truelift-offline.zip`, `TrueLift_deck.pdf`, `TrueLift_one_page.pdf`.
  The zip was rebuilt from the deployed `gh-pages` site (`git -c core.autocrlf=false archive`; plain `git archive`
  on Windows turns LF into CRLF), so its `build.json` names `8ac3ca4`. README and runbook link the download;
  handoff step 7 marked done, step 6 asks for a merge commit, not a squash.
- Files: `README.md`, `docs/handoff.md`, `docs/pitch/runbook.md`, `.claude/context/`.
- Checked: offline browser tests 8 of 8 on the new bundle; the zip's contents equal the folder; the three files
  downloaded back from the release match the SHA-256 in the notes and GitHub's digests.
- Numbers changed: none.
- Next / open: the team's items in `docs/handoff.md`.

## 15 Nov 2026 · Kshitish (Claude Opus) · branch kshitish (deploy verified, page race fixed)
- Did: CI deploy of `c8a873b` published the 32-restaurant demo; its public-URL browser test failed because a click on
  "Create an offer" during a restaurant switch landed on the old screen over a real network. Fix: the screen shows a
  loading placeholder while a restaurant loads (`openRestaurant`), and the test waits for the new restaurant.
  Architecture: request sequence, capacity table (4 new claims), demo modes; README links the video.
- Checked: Playwright 20 of 20 locally and 4 of 4 against the public URL; fresh clone from GitHub installs, passes the
  tests and reproduces the golden snapshot; claims 187 of 187.
- Numbers changed: none.
- Next / open: the team's items in `docs/handoff.md`; release tag needs the owner's go-ahead.

## 15 Nov 2026 · Kshitish (Claude Opus) · branch kshitish (pitch, video, export, handoff)
- Did: pitch in `docs/pitch/` generated from reports by `scripts/make_deck.py` (12 + 8 slides as HTML, PDF and
  editable PPTX; speaker notes with timing, five-minute cut and three registers; one-pager with QR), `runbook.md`,
  30-question bank (65 new claims in `docs/claims.yml`; the ledger caught a wrong "0 sample-ratio alarms": it is 4 in
  2,736 weekly checks, 0 in the first four weeks). `scripts/make_video.py` records the guided demo with generic names
  (D5) -> `docs/pitch/demo.mp4` and retakes the README screenshots. Full 32-restaurant export (self-check passed),
  offline bundle (62.8 MB zip). CI exports all 32 only on deploy runs (D15 amended; the 14 Nov run timed out at 60
  min). Error-tracking flag `TRUELIFT_SENTRY_DSN` (off by default, uv group `ops`, plan D9). WhatsApp text keeps
  generic names under `#names=generic`. DoorDash ghost-ads comparison added to the write-up. `docs/handoff.md`.
- Checked: Playwright 20 of 20 (static, phone, offline-file, offline-http, live); claims 183 of 183; tables;
  `tests/test_pitch.py`, `tests/test_error_tracking.py`. Not checked yet: CI deploy run and the public URL.
- Numbers changed: none (pitch numbers come from the frozen reports).
- Next / open: `[deploy]` push, verify the public URL with Playwright, clean-clone check; team items in `docs/handoff.md`.

## 15 Nov 2026 · Kshitish (Claude Opus) · branch kshitish (number freeze, documents, field kit)
- Did: froze the numbers of the 14 Nov night run: `reports/` and the model `data/processed/model.pkl` (+ `.sha256`),
  now committed (un-ignored; D15). README, STATE and method-doc tables rendered from reports; claims ledger
  `docs/claims.yml` (118 claims) checked by `scripts/check_claims.py`. New docs: method_and_evidence (renamed write-up,
  pointer at the old path), what_we_tested (all 50 findings with their guard tests), integration_blueprint, events
  schemas, openapi.json, privacy_and_fairness, decisions 0001-0010, CHANGELOG; model card, simulator datasheet and
  architecture updated (percentage offers, renewal, Hillstrom, privacy rule, shadow kit). Shadow kit and sample events
  (`scripts/shadow_measure.py`, `data/sample/`), pilot size. Field kit `docs/field_research.md` + `docs/field_research/`
  (EN sheet, HI/GU drafts, consent, cards, notes, outlets, short form; not yet conducted). Golden re-recorded (only
  the new `percentage_offers` section differs). Suggestion card links to the Evidence page's inflation note.
- Checked: see the commit's test run (full pytest incl. slow, claims, tables, lint). Not checked: export of the 32
  restaurants, browser tests on it, deploy.
- Numbers changed: every simulator number now comes from the final run; DEVLOG "Corrections" lists what moved.
- Next / open: export + offline bundle + browser tests + `[deploy]`; pitch (deck, questions, video, one-pager).

## 14 Nov 2026 · Kshitish (Claude Opus) · branch kshitish (percentage offers, real data, renewal, languages)
- Did: percentage-off-with-cap offers (`Design.pct`; engine scores them at their average discount per use; sim
  takes min(pct x bill, cap); create screen "% off up to Rs" chips; export keys `60p30-...`; Money page rows;
  pipeline `percentage_offers` with a usual and a proportional variant). Real data: `scripts/get_data.py`
  (SHA-256), `scripts/validate_uplift.py` rewritten (Criteo + Hillstrom, five rankings incl. response model,
  scikit-uplift qini_auc_score, 200 bootstraps, 5 splits), `tasks.py realdata`, uv group `validation`.
  Renewal with evidence (`POST /api/v1/offers/{id}/renew`, same control group, weeks continue) and a what-if card
  (A09 D3/D4). Language drafts hi/kn/gu (`truelift/i18n.py`, `static/i18n/`), off until reviewed (D4, `#lang=hi`).
- Checked: 160 fast tests, ruff, pyright; quick pipeline equals the golden snapshot except the new section.
  Not checked yet: freeze run (in progress), browser tests, export.
- Numbers: real-data reports new (`reports/uplift_validation_{criteo,hillstrom}.json`); simulator numbers land
  at the freeze commit.
- Next / open: freeze commit (reports, model, README/plan tables, DEVLOG), export, deploy, M4 docs.

## 14 Nov 2026 · Kshitish (Claude Opus) · branch kshitish (fleet calibration, M3 UI, docs)
- Did: weekly measurement recalibrated across running offers (split halves for noise, own-vs-model spread for
  model error; `measurement_study._fleet_calibration`, engine `fleet_sigma_factor`, placebo offers too). Zomato-style
  restyle (measured on zomato.com; bundled Figtree OFL font; CSP self only), Evidence page with every new result,
  Operations tab, Money page computed with commission-base and food-cost switches, guided demo Back/jump keys,
  deep links, offline bundle (`scripts/build_offline.py`, file:// and local server), Playwright 5 projects,
  `scripts/render_tables.py`, docs (architecture, model card, simulator datasheet), LICENSE (MIT), NOTICE, SECURITY.
- Checked: 130 fast tests, lint, pyright; offline browser tests passed on the old export. Not checked: slow suite on
  this exact commit, full browser suite, export of the 32 demo restaurants.
- Numbers: NOT frozen yet. The final full run was still going (reports/ and model.pkl uncommitted); README and plan
  tables are markers to render with `python scripts/render_tables.py` after it (README/plan edits left uncommitted).
  Full-run findings so far: 4-week combined error Rs 2,054 vs model 2,212 vs own 4,160, coverage 90%; selection
  advantage overstated 5.3x (79% of suggestions truly better); TrueLift commission now above blanket.
- Next / open: finish the final run, render tables, update DEVLOG/plan/STATE numbers, slow tests, export 32
  restaurants, build offline zip, deploy with [deploy]; renewal with evidence and languages not done.

## 14 Nov 2026 · Kshitish (Claude Opus) · branch kshitish (M2 Brand Pack, monitoring, experiments)
- Did: Brand Pack reward gets its own control group among regulars (REWARD_SALT; sim, serving, exposure log,
  `measure_reward`, second weekly line in API/WhatsApp/page; TL-016). `truelift/monitoring.py`: drift report
  (PSI per input, drift.json/drift.html, fails the pipeline above 0.25; a test brings back the TL-007 window
  fault and sees it fail) and weekly guardrails with thresholds (guardrails.json). `scripts/experiments.py`
  (oracle, depth-choice, variance-reduction, holdout-draws, retrain-loop, depth-test; sim has depth arms),
  `scripts/bench_latency.py` (real HTTP), `tests/load/locustfile.py`. A model trained on other inputs is now
  refused at load (the service used to report ready, then fail on the first prediction).
- Checked: fast + slow tests, golden re-recorded (Brand Pack hold-out changes the shadow history). Experiments
  run on the quick market only so far.
- Findings (quick): oracle captured 70% (docs say ~60%); letting the model pick the size now RAISES own-offer
  profit (3.19 -> 4.01 L) but not market profit (1.95 -> 1.96 L), losing offers 15 -> 38 (D6 note); noise cut
  from the adjustment ~6% (docs say 27%); holdout draws centred (mean error Rs 1, se 103), coverage 75%;
  retraining on two live weeks would be promoted; a 4-week size test picks the better size 61% (52% small).
- Next / open: final full run of everything, then update README/DEVLOG/plan numbers together (rule 5).

## 14 Nov 2026 · Kshitish (Claude Opus) · branch kshitish (M2 market analyses)
- Did: pipeline gains Zomato-weight frontier (lambda 0.5/1/2), OTP-consent attrition (blind and informed
  declines, break-even share), Zomato's ledger (platform-incremental share of extra orders; unmeasured
  co-funding flagged as a pure transfer; control group's cost), partial adoption 10%/30%, history that moves,
  fairness by segment with loyalty gap and three priced mitigations, control-set option (TL-019); seeds 8-11
  and a pre-discount-commission run in parallel (full run only). New: `scripts/sensitivity.py` (8 assumptions,
  tornado data, boundaries in words), `scripts/benchmark_learners.py` (random/response/rule/S/T/X/DR/oracle),
  `model.ALLOWED_FEATURES` + `tests/test_fairness.py`, `tests/test_market.py`, tasks `sensitivity`, `benchmark`.
- Files: scripts/run_pipeline.py, scripts/sensitivity.py, scripts/benchmark_learners.py, truelift/engine.py
  (quote has zomato_contribution_change; best_design zomato_weight), truelift/model.py, truelift/training.py
  (engine uses the market's Terms), tests/*, tasks.py, pyproject.toml/uv.lock (threadpoolctl declared).
- Checked: 121 fast tests; slow tests and golden (re-recorded); ruff, pyright. Not checked: full pipeline.
- Numbers changed: quick golden only (new sections). Findings (quick): frontier flat (weighting Zomato buys it
  nothing, restaurants lose); co-funding without a change in offers creates no order; Brand Pack for regulars
  closes the loyalty gap at no own-offer cost; sweep boundaries incl. 5 menus per occasion (forecast 1.32x truth).
- Next / open: Brand Pack control group (M2 step 14), guardrails/drift, real data, final run, then M3 UI.

## 14 Nov 2026 · Kshitish (Claude Opus) · branch kshitish
- Did: M1 of Kshitish's audit plan. Pinned `uv` environment; service v1 (typed `/api/v1` hooks, RFC 9457 errors,
  per-visitor sessions, OTP expiry and attempt limit, hash-chained consent ledger, exposure log, decision-table
  serving, health/readiness/metrics); tests split by area + golden + Schemathesis fuzz; Playwright suite (static
  and live); `tasks.py`, Makefile, Docker, pre-commit, CI with a gated deploy (D15). Fixed: CSP blocked Google Fonts;
  `run_week` returned 500 for a narrow design with no eligible visit in a week (found by CI, smaller market).
- Files: `truelift/*` (9 new modules), `scripts/` (run_pipeline, export_static, compare_reports), `tests/*`,
  `tests/ui/*`, `tasks.py`, `Dockerfile`, `.github/*`, `pyproject.toml`, `uv.lock`, CLAUDE.md, README (Run it).
- Checked: 93 fast tests, golden, fuzz, ruff, pyright, pre-commit; full pipeline equals `reports/`; browser suite
  on `site/` (12 restaurants) and the live service. Not checked: Docker build (no Docker locally; CI builds it).
- Numbers changed: M1 none. M2 under way on `kshitish` (committed `reports/` stay as on main until the
  final run): co-funding fix (TL-003) changes only the co-funding scenario; one feature window
  definition (4 and 8 weeks), 8 status-quo weeks, rolling shadow features, point-in-time quote input (TL-007);
  top-up value fitted on menu visits (TL-020: 0.50, the simulator truth; was 0.55-0.60).
  Forecast check (TL-006): quote/truth 0.59 -> 0.91 for TrueLift designs once the shadow phase explores
  the create screen's depths (10-25% of the order) at today's share of offers (40%).
  Monotone constraints adopted; competition feature tried, not adopted (A05 L8; numbers in model.py).
  Customer-level variance (TL-029); predicted gains calibrated on shadow-phase holdouts; TrueLift offers only
  with a >= 60% chance of making money (TL-018): losing offers 71 -> 18 at the same total profit (quick).
  Weekly measurement checked by an A/A test (placebo offers): noise from the model's expected variance,
  calibrated by split halves; pause only on always-valid own evidence; "probably losing" warning; false pauses
  25% -> 1.7% per consent period (quick). New verdict codes reach the page (app.js).
- Next / open: rest of M2 (numbers change once, at a single freeze), M3 UI restyle (tell Yash first).

## 13 Nov 2026 · Yash (Claude Opus) · branch main
- Did: added this shared context (`CLAUDE.md`, `.claude/context/`), project settings that turn off Claude
  attribution, and `.claude/hooks/git_guard.py` (blocks AI attribution, force-pushes, and commits that do
  not update the context). Prepared a one-time rewrite that drops the Claude co-author line from old
  commits (main, kshitish, gh-pages, tag); Claude's force-push was blocked by permissions, so Yash runs it.
- Files: CLAUDE.md, .claude/, .gitignore, README.md (export command lists the 12 demo restaurants).
- Checked: hook tested with 15 sample inputs; rewritten commits have identical trees, authors, dates.
- Numbers changed: none.
- Next / open: teammates pull with `git pull --rebase`; fill "Who is on what" in STATE.md.

## 13 Nov 2026 · Yash (Claude Opus) · branch main
- Did: UI redesign in Zomato partner-app style; guided demo (10 steps); How it works tab; clearer weekly
  results with an estimate-vs-truth chart; 12 restaurants on the static site; `sget` retries a 404 once.
- Files: truelift/static/*, scripts/export_static.py, tests/ui_check.js, README.md, DEVLOG.md.
- Checked: ui_check.js and a 12-restaurant sweep pass on localhost and the live site.
- Numbers changed: none (UI only).

## 13 Nov 2026 · Yash (Claude Opus) · branch main
- Did: submission prep. DEVLOG.md for judges, README "For judges" table, tag `round2-submission`;
  repo made public; real restaurant names back with "Simulated data" labels (D7); Criteo real-data check.

## 12 Nov 2026 · Yash (Claude Opus) · branch main
- Did: built everything from Round 1 drafts: research pass, economics, simulator, uplift model, engine,
  API, UI, tests, pipeline, plan, GitHub Pages. First run lost to the simple rule; fixed basket bias and
  top-up value, then D6 (owner keeps discount size). Full story: DEVLOG.md steps 1–11.
