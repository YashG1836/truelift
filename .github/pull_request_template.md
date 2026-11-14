## What changes and why

<!-- One or two sentences: the cause, then the effect. -->

## Checks

- [ ] `python tasks.py test --all` passes (fast tests, golden numbers, contract fuzzing)
- [ ] `python tasks.py lint` passes (Ruff, Pyright)
- [ ] UI changes: browser tests pass (`cd tests/ui && npx playwright test`), checked at 390 px width
- [ ] Numbers changed? They come from a re-run of the pipeline, the golden snapshot is re-recorded,
      and README, DEVLOG, the plan and `.claude/context/STATE.md` say the same thing
- [ ] `.claude/context/` updated (SESSIONS entry; STATE and DECISIONS where they changed)
- [ ] Every screen and document still says the outcomes are simulated
