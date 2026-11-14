# TrueLift: start here (for every teammate's Claude)

Claude Code loads this file automatically in this repo. It is the shared memory of Team Banana
(Yash Goyal, Bhavay Goyal, Kshitish Madbhavi). Read it and the current state below before doing
anything, so nobody has to re-explain the project. Keep it true: the rules at the end say how.

**Project.** IITGN × Eternal hackathon, Round 2 (we are one of 10 shortlisted teams; the other 9
are operations topics). Problem: restaurant discounts on Zomato are judged by the orders that *use*
them, not the orders they *create*. Since Aug 2026 restaurant-funded offers need the owner's OTP
approval, so an owner who cannot see whether an offer pays will stop approving. TrueLift forecasts,
targets and measures each offer by the extra orders and profit it creates, inside that OTP flow.

- Live demo: https://yashg1836.github.io/truelift/ (branch `gh-pages`, generated; do not edit by hand)
- Code: https://github.com/YashG1836/truelift (public). Write-up: `TrueLift_Round2_Plan.md`.
  Judge-facing build story: `DEVLOG.md`. Round 1 PDF: `docs/round1_problem_statement.pdf`.

## Shared context (read in this order)

1. `.claude/context/STATE.md`: what is true now (links, numbers, open tasks, who is on what). Loaded below.
2. `.claude/context/DECISIONS.md`: settled decisions and why. Read before changing method or scope.
3. `.claude/context/SESSIONS.md`: what each session did, newest first. Read the top 3 entries.

@.claude/context/STATE.md

## Repo map

| Path | What it is |
|---|---|
| `truelift/economics.py` | Money of one order (commission 25% + 18% GST on it, food cost 37%, who funds the discount) |
| `truelift/sim.py` | Simulated Bengaluru market: 300 real 2019 listings, synthetic customers, exact counterfactuals |
| `truelift/assignment.py` | The hashed (customer, offer) control group, shared by simulator, service and measurement |
| `truelift/features.py` | Customer and restaurant features from the order history (aggregates computed once) |
| `truelift/model.py` | Uplift model (T-learner, HistGradientBoosting), Qini, model bundle with SHA-256 check |
| `truelift/training.py` | History -> model -> calibration (used by the pipeline and the tests) |
| `truelift/engine.py` | Quote, design search (owner's depth fixed), decision table, serving, weekly measurement, verdicts |
| `truelift/api.py` | FastAPI routes under `/api/v1` (hooks + demo), RFC 9457 errors, `/healthz` `/readyz` `/metrics` |
| `truelift/schemas.py`, `settings.py` | Typed request/response models (the OpenAPI contract); configuration from `TRUELIFT_*` env vars |
| `truelift/state.py`, `store.py`, `demo.py` | Sessions and offers; SQLite consent ledger (hash-chained) and exposure log; simulated weeks and payout |
| `truelift/observability.py` | JSON request logs, Prometheus metrics, security headers |
| `truelift/monitoring.py` | Input drift (PSI per feature, drift.html) and weekly guardrails with thresholds |
| `truelift/static/` | Partner-app UI (index.html, app.js, style.css): guided demo, How it works, Evidence, Money maths |
| `scripts/` | build_restaurants, run_pipeline (+ measurement_study), sensitivity, benchmark_learners, experiments, bench_latency, export_static (static site), validate_uplift (Criteo), compare_reports |
| `tests/` | pytest by area (economics, simulator, engine, api, consistency, statistics, market, fairness, monitoring), `test_golden.py` (numbers), `test_fuzz.py` (contract); `tests/ui/` Playwright browser tests; `tests/load/` Locust; `ui_check.js` (older browser check) |
| `tasks.py`, `Makefile` | One entry point for setup, test, lint, pipeline, serve, export, reproduce, golden, docker |
| `Dockerfile`, `compose.yaml` | The service in a container (non-root, health check) |
| `.github/workflows/` | CI (lint, tests on Linux and Windows, golden + fuzz, browser tests, Docker, gated deploy), CodeQL |
| `reports/` | Pipeline outputs. Every number in docs and UI must trace to a file here |
| `data/processed/restaurants.csv` | The 300 restaurants (public listing fields only) |

Not in git (each person builds locally): `.venv/`, `data/raw/`, `data/processed/model.pkl` (+ `.sha256`),
`data/processed/serving_*.npz` (start-up cache), `site/`, `LOG.md` (Yash's private log).

## Commands

```bash
uv sync                                  # pinned environment from uv.lock (or: pip install -r requirements-dev.txt)
python tasks.py pipeline                 # ~10 min: simulate, train, evaluate, scenarios and 5 seeds -> reports/, model.pkl
python tasks.py sensitivity              # ~5 min: eight assumptions low/high -> reports/sensitivity.json
python tasks.py benchmark                # ~1 min: uplift learners vs the truth -> reports/learner_benchmark.json
python tasks.py experiments              # ~15 min: oracle, depth choice, noise, holdout draws, retraining, depth test
python tasks.py latency                  # starts the service, times serve and quote over HTTP -> reports/latency.json
python tasks.py serve                    # full service + UI at http://localhost:8000 (API docs at /docs)
python tasks.py test                     # fast tests (~20 s), must pass before any push; --all adds golden + fuzz
python tasks.py lint                     # ruff check, ruff format --check, pyright
python tasks.py reproduce                # re-run the pipeline in a temp folder, compare with reports/ (1e-6)
python tasks.py export                   # site/ with the 12 demo restaurants (~9 min); ids as arguments for fewer
python tasks.py golden                   # re-record tests/golden/ after an intended change in the numbers
cd tests/ui && npm ci && npx playwright install chromium && npx playwright test   # browser tests, static + live
```

Publish the demo: CI publishes from branch `kshitish` after every check passes, for a commit whose
message contains `[deploy]` (or a manual run with deploy=true); it refuses a site built without the
committed model (DECISIONS D15). By hand: clone branch `gh-pages` into a temp folder,
`rsync -a --delete --exclude .git site/ <temp>/`, commit, normal `git push`, then run the browser tests
with `UI_PROJECTS=public TRUELIFT_PUBLIC_URL=<url>`.
UI must keep `/static/app.js` and `/static/style.css` paths in index.html (export_static rewrites them).
API routes live under `/api/v1/`; the page and the static export use the same paths.

## Team rules (every Claude follows these, every session)

1. **Start:** `git pull --rebase` first. Read STATE.md and the top of SESSIONS.md. Work on your own
   branch (`kshitish`, `bhavay`, ...) unless the person you work for says main. Before editing a
   file someone else is listed on in STATE.md ("Who is on what"), tell your person.
2. **Keep the context current, end to end.** Whenever you change code, data, numbers, the site or docs:
   - add an entry at the **top** of `.claude/context/SESSIONS.md` (template in that file);
   - update `.claude/context/STATE.md` wherever it is now wrong (numbers, links, tasks, who is on what);
   - add to `.claude/context/DECISIONS.md` when the team decides something that should not be re-argued;
   - update this file if the repo map, commands or rules change.
   Do it in the same commit as the change. A hook blocks `git commit` when nothing in `.claude/context/`
   changed; for a truly trivial commit (typo) put `[skip context]` in the message.
   Write facts another Claude can act on (paths, numbers, commands), not a diary. Keep STATE.md under ~80 lines.
3. **No AI attribution anywhere.** No `Co-Authored-By: Claude ...`, no `noreply@anthropic.com`, no
   "Generated with Claude Code" in commits or PR text. `.claude/settings.json` turns it off and the hook
   blocks it.
4. **History is shared.** Never force-push, rebase pushed commits or delete branches without the whole
   team agreeing. To integrate, use `git pull --rebase` on your own unpushed commits only.
5. **Numbers.** Never type a result by hand. Re-run the script, read it from `reports/`, and show the
   calculation (the team's rule: every figure can be checked). If a number changes, update README,
   DEVLOG, the plan and STATE.md together.
6. **Honesty about data.** Restaurant names and listing details are real public 2019 listings;
   customers, orders and profits are simulated. Every screen and doc must keep saying so.
7. **Writing style** (Yash's preference): simple, formal, plain words, cause → effect sentences, explain
   jargon, no filler, no template-looking layouts (eyebrow labels, decorative tables).
8. **UI style:** Zomato partner-app look (tokens at the top of `style.css`: red `#e23744` for actions only).
   Data series use blue/grey, never brand red. Check desktop and 390 px phone width.
9. **Done means checked:** tests pass, `ui_check.js` passes for UI changes, and the live site is
   re-checked after publishing. Say what you did not check.
