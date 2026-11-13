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
| `truelift/model.py` | Uplift model (T-learner, HistGradientBoosting) and Qini |
| `truelift/engine.py` | Quote, design search (owner's depth fixed, 34 versions), serving, weekly measurement, calibration |
| `truelift/api.py` | FastAPI service: Zomato-style hooks (quote, offers, approve/OTP, serve, run_week, decision) + demo endpoints |
| `truelift/static/` | Partner-app UI (index.html, app.js, style.css): guided demo, How it works, Evidence, Money maths |
| `scripts/` | build_restaurants, run_pipeline, export_static (static site), validate_uplift (Criteo real data) |
| `tests/` | `test_truelift.py` (11 pytest tests), `ui_check.js` (browser check with playwright-core) |
| `reports/` | Pipeline outputs. Every number in docs and UI must trace to a file here |
| `data/processed/restaurants.csv` | The 300 restaurants (public listing fields only) |

Not in git (each person builds locally): `.venv/`, `data/raw/`, `data/processed/model.pkl`, `site/`, `LOG.md` (Yash's private log).

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/run_pipeline.py            # ~6 min: simulate, train, evaluate -> reports/, model.pkl
.venv/bin/uvicorn truelift.api:app --port 8000      # full service + UI at http://localhost:8000
.venv/bin/python -m pytest -q                       # 11 tests, must pass before any push
node tests/ui_check.js reports/ui http://localhost:8000/   # browser check (npm i playwright-core; CHROME=path)
.venv/bin/python scripts/export_static.py 233 248 17 142 191 273 84 172 57 146 283 31   # site/ (~12 restaurants)
.venv/bin/python scripts/export_static.py --assets  # refresh only the UI files in site/
```

Publish the demo: clone branch `gh-pages` into a temp folder, `rsync -a --delete --exclude .git site/ <temp>/`,
commit, normal `git push`. Then run `ui_check.js` against the live URL.
UI must keep `/static/app.js` and `/static/style.css` paths in index.html (export_static rewrites them).

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
