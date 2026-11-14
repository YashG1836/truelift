# Current state

Last updated: 14 Nov 2026 by Kshitish (Claude), M2 market batch. Overwrite lines that become wrong; do not append history here
(history goes in SESSIONS.md).

## Status
- Round 2 submission is complete and live. Tag `round2-submission` marks the submitted version
  (before the UI redesign); `main` has the redesigned UI.
- Branches: `main` (shared), `kshitish` (Kshitish's work), `gh-pages` (generated demo site, do not edit).
- Branch `kshitish` (not merged yet): API under `/api/v1/` (old paths gone), model bundle with a `.sha256`
  sidecar (rebuild with `python tasks.py pipeline` after switching to it), `uv` environment, `tasks.py`,
  93 fast tests + golden numbers + contract fuzzing + Playwright, CI in `.github/workflows/`. Numbers unchanged.
- Teammates ksawesome (Kshitish) and BhavayGoyal have write access (invites sent 12 Nov).
- One-time history rewrite (13 Nov, run by Yash): drops the Claude co-author line from the old commits;
  files, authors and dates stay the same, hashes change. It is done when
  `git log origin/main --format=%B | grep -c anthropic` prints 0. If your clone is older than that:
  `git stash` (if you have uncommitted work), `git pull --rebase`, `git stash pop`. Never merge old history back.

## Headline numbers (source: `reports/evaluation.json`, per week, 300 simulated restaurants)
| | Blanket | Rule: new customers only | TrueLift |
|---|---|---|---|
| Offers that pay for themselves | 130 | 211 | 242 |
| Own-offer restaurant profit | ₹6.94 L | ₹7.34 L | ₹7.65 L |
| Restaurant profit vs no offers (market) | +₹2.46 L | +₹3.96 L | +₹4.85 L |
| Discount given | ₹16.7 L | ₹10.8 L | ₹10.0 L |
| Zomato commission vs no offers | +₹6.45 L | +₹5.95 L | +₹6.38 L |

- Measurement: 80% ranges cover truth 67% / 79% / 81% after weeks 1 / 2 / 4; "keep" verdicts right 87 / 90 / 92%.
- Real data (Criteo, 4.2M unseen users, `reports/uplift_validation_criteo.json`): visits Qini 0.339 vs 0.005
  random, top 30% holds 84% of extra visits; purchases Qini 0.056 vs 0.015 (67%).
- Example week (`truelift/economics.py`): ₹400 order, restaurant keeps ₹134 full price, ₹91.70 with ₹60 off.
  Blanket offer: restaurant −₹210, Zomato +₹1,500; TrueLift: +₹2,101 and +₹2,550.
- Break-even share of extra orders (money page): 21% / 32% / 42% / 53%.

## Demo site
- 12 restaurants: 233 Burger King (default), 248 Domino's, 17 Empire, 142 On The Nose, 191, 273, 84, 172,
  57, 146, 283, 31. ~18 MB of precomputed JSON in `site/data/<id>/`.
- Guided demo: 10 steps, keys → / Enter / Esc. Tabs: Demo, How it works, Evidence, Money maths.
- Last full check (13 Nov): `tests/ui_check.js` and a 12-restaurant sweep passed on the live site.
  Truth inside the range after 4 weeks for 10 of 12 (Beijing Bites and Empire outside; expected at ~80%).

## Open tasks (owner in brackets; change when you pick one up)
1. [team] Interview 6–8 restaurant owners: offer report, OTP screen, payout statement (plan §7).
2. [team] Send Eternal the questions in plan §10 (commission before or after discount: break-even 32% vs 45%
   at 15% off; anonymised offer logs or a shadow test).
3. [team] Rehearse the 5-minute demo (plan §8) with the guided demo; local server as backup.
4. [open] Customer-level randomised depth test (two discount sizes at random), see DECISIONS D6.
5. [open] Control group for Zomato's own (platform-funded) discounts, see DEVLOG step 8.

## Known limits (say these if asked)
- All outcomes are simulated; only the Criteo check uses real randomised data (ads, not restaurant offers).
- Brand Pack is rarely chosen (2 of 300): in the simulator loyal customers are not very price sensitive.
- Small restaurants: a 10% holdout alone gives ±5.4 points in a week on a 3-point effect, so the estimate
  leans on the model early and on the restaurant's own holdout later.

## Who is on what (update when you start or finish; prevents two people editing the same file)
- Yash: idle after the UI iteration and this shared-context setup (13 Nov).
- Kshitish: branch `kshitish`, implementing his audit plan. M1 done (service, tests, CI). M2 science under way:
  measurement, selection, market analyses, sensitivity sweep and learner benchmark done; left: Brand Pack
  control group, guardrails/drift, real data, final run and freeze (all number changes land at one freeze).
  Then M3 restyle of `truelift/static/` (Yash's last area: tell Yash first), M4 docs and pitch.
  Files: `truelift/*`, `scripts/*`, `tests/*`, `.github/*`.
- Bhavay: not started in the repo yet. Add your area here.
