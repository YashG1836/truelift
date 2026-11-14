# Changelog

All notable changes, newest first. Versions follow semantic versioning; dates are IST.

## 2.0.0 (branch `kshitish`, 14–15 November 2026)

The Round 2 build after a full self-audit (50 findings, numbered TL-001 to TL-050). Each fix is
listed with the test or check that guards it in `docs/what_we_tested.md`. Numbers moved; the
corrections, before and after, are in `DEVLOG.md`.

### Added
- Service v1: typed `/api/v1` hooks with an OpenAPI contract (`docs/openapi.json`), RFC 9457 errors,
  per-visitor sessions, OTP expiry and attempt limit, idempotent approval and weekly runs,
  `/healthz`, `/readyz`, `/metrics`, security headers.
- Serving from a decision table built at approval: a lookup and a hash on the customer's path, no
  model.
- Hash-chained consent ledger and exposure log (SQLite); the weekly measurement reads the logs.
- Weekly measurement recalibrated every week across running offers; verdicts keep, too early,
  probably losing, pause; pause only on the offer's own always-valid evidence; sample-ratio check.
- Brand Pack reward with its own control group and its own weekly line.
- Percentage-off-with-cap offers on the create screen, in the engine, the simulator and the Money page.
- Renewal with measured evidence (`POST /api/v1/offers/{id}/renew`) and a "what if you had run your
  version" card.
- Owner texts in Hindi, Kannada and Gujarati as drafts, off until a native speaker reviews them.
- Market analyses: Zomato-weight frontier, owners declining OTP approval, Zomato's ledger,
  measure-only policy, partial adoption, history that moves, five market seeds, fairness by segment
  with three priced mitigations, sensitivity sweep of eight assumptions, learner benchmark,
  experiments (oracle, size choice, variance reduction, holdout draws, retraining, size test).
- Real-data checks on Criteo and Hillstrom with five rankings, intervals and scikit-uplift's Qini.
- Monitoring: input drift (PSI) and weekly guardrails; an Operations tab.
- Zomato-style interface (measured on zomato.com, open font bundled), Evidence page, Money maths
  with switches, guided demo with Back and keys, deep links, an offline bundle that opens from a file.
- Tests by area, golden numbers, contract fuzzing, statistical tests, Playwright suites (static,
  phone, offline from a file and over a local server, live, public URL), a load test.
- `tasks.py`, Makefile, Docker, CI on Linux and Windows with a gated deploy, CodeQL.
- Documents: architecture, integration blueprint with event schemas and a shadow kit, decision
  records, model card, simulator datasheet, privacy and fairness, what we tested, field kit, handoff.
- Pitch (`docs/pitch/`): a deck (HTML, PDF and editable PPTX) and a one-page summary generated from
  `reports/`, speaker notes, a demo runbook, thirty questions with checked answers, and a captioned
  recording of the guided demo.
- Optional error tracking behind `TRUELIFT_SENTRY_DSN` (off by default; errors only, no personal data).

### Fixed
- TL-001: concurrent quotes could read each other's cached predictions.
- TL-003: the simulator paid Zomato's co-funding on every redemption, not only for customers new
  to Zomato.
- TL-004: serving and the measurement used different control groups.
- TL-006, TL-007: forecasts were low because the shadow phase explored discount sizes owners do not
  use and features were computed differently in training and serving.
- TL-009, TL-017: offers were auto-paused on noise; repeated weekly looks inflated false pauses.
- TL-012: invalid designs were accepted; TL-008, TL-024, TL-037: sessions, offer ids and weekly runs
  were shared or could repeat.
- TL-016: the Brand Pack reward was measured together with the discount.
- TL-018: the best of 34 noisy forecasts was presented without its range of error.
- TL-020: the value customers put on topping up to a minimum order was fitted on the wrong unit.
- TL-022 to TL-050: interface, documentation and portability findings (see `docs/what_we_tested.md`).

### Changed
- The public demo has 32 restaurants (six localities, five price bands).
- The README and the method document take their results tables from `reports/`.

## 1.0.0 (tag `round2-submission`, 13 November 2026)

The Round 2 submission: simulator, uplift model, engine, FastAPI service, partner-app page, static
demo on GitHub Pages, method write-up and development log.
