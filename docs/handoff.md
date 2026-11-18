# Handoff: what the team still has to do

Branch `kshitish` holds the finished build: the service, the evidence, the documents, the public and
offline demos, and the pitch. These are the things only the team, or the repository's owner, can
do. Each says why it matters and when it is done.

## Before the deadline (18 November 2026)

1. **Rehearse.** Three runs with `docs/pitch/runbook.md`: timing, the failure drill (Wi-Fi off,
   server down, wrong OTP, projector at 1024 × 768), and hostile questions from someone outside the
   team. Each member owns ten questions of `docs/pitch/questions.md` and answers them without notes.
   *Done when* the talk ends 30 seconds inside the limit twice in a row.
2. **Interview six to eight restaurant owners** with the kit in `docs/field_research/` (consent script
   first; question sheets; comprehension cards). The first took place on 17 November with the
   manager of a chain outlet in Gandhinagar (photos in `docs/field_research/photos/`); its note is
   still to be written up. Fill the tables in `docs/field_research.md` from the
   written notes only, as counts. If a finding changes the product or the pitch, list the change.
   *Why:* every rupee in the evidence is simulated; owners are the only real evidence we can collect
   this week, and one payout statement settles the commission question. *Done when* at least six
   notes are written up, or the table says how many were done and why not more.
3. **Ask Eternal** the questions in `docs/method_and_evidence.md` §10 (commission base, OTP screen,
   logs for the shadow kit).
4. **Bhavay: commit your own work** under your own name, so the history shows three contributors.

## When the team is ready

5. **Review the Hindi, Kannada and Gujarati drafts** (`truelift/static/i18n/{hi,kn,gu}.json`, and the
   Hindi and Gujarati field-kit sheets) with native speakers. Then switch them on (decision D4):
   `TRUELIFT_LANGUAGES=1` for the live service, and the same variable in the export step's `env` in
   `.github/workflows/ci.yml` before the next `[deploy]`, so the public demo offers them.
6. **Merge `kshitish` into `main`** through a pull request; decision D13 replaces D5 at the merge.
   Use a merge commit, not a squash: a squash drops the individual commits and their authors, and
   leaves the tag `v2.0.0` outside `main`'s history. Never merge the history from before the
   13 November rewrite. After the merge, if `main` should
   publish the demo, change `refs/heads/kshitish` to `refs/heads/main` in the deploy job of
   `.github/workflows/ci.yml`.
7. **Release: done on 15 November.** `v2.0.0` is an annotated tag on `8ac3ca4`, the commit the
   public demo is built from: https://github.com/YashG1836/truelift/releases/tag/v2.0.0. It has the
   notes of `CHANGELOG.md` 2.0.0 and three files: `truelift-offline.zip`, `TrueLift_deck.pdf` and
   `TrueLift_one_page.pdf`, with SHA-256 checksums in the notes. The tag `round2-submission` stays
   where it is. For a later release, make the offline zip from the deployed site of the tagged
   commit, so that its `build.json` names that commit: extract the `gh-pages` branch into `site/`
   with `git -c core.autocrlf=false archive origin/gh-pages`, then run
   `python scripts/build_offline.py`.

## Repository settings (needs admin on `YashG1836/truelift`)

8. **Branch protection** for `main` (and `kshitish` until the merge): require a pull request, require
   the CI checks (lint and types, the four test jobs, golden numbers and fuzzing, the browser job,
   Docker), block force pushes and deletion.
9. **Pages**: source is the `gh-pages` branch, root folder (CI publishes there; decision D15).
10. **Security**: turn on Dependabot alerts and security updates, secret scanning and push
    protection. Code scanning already runs (`.github/workflows/codeql.yml`).

## Optional

11. **Coverage service.** CI already fails below 85% line coverage; the Codecov app only adds a
    badge and pull-request comments.
12. **Error tracking** for a hosted service: set `TRUELIFT_SENTRY_DSN` and run `uv sync --group ops`.
    It sends errors only, never request bodies or customer ids (`truelift/observability.py`). The
    static and offline demos have no server and never send anything.
13. **Hosting the live service** was decided against (decision D3): it runs locally
    (`python tasks.py serve`) or in Docker (`docker compose up --build`).

## What to say if asked

The known limits are in `.claude/context/STATE.md` and `docs/what_we_tested.md`: all outcomes are
simulated; the suggested version's stated advantage runs well above its true advantage; the
four-week estimate inherits a bias from the model; small restaurants need weeks of their own data.
