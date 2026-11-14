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
