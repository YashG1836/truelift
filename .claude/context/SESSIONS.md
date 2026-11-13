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
