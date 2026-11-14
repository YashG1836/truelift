# Decisions (settled; do not re-open without new evidence and the team's agreement)

Format: ID. Decision. Why. Add new ones at the bottom with a date and who decided.

- D1. Scope is restaurant-funded discounts on Zomato food delivery only (no Blinkit, District, cancellations).
  Why: one sharp problem beats a broad one; it is the only pricing/economics topic among the 10 teams.
- D2. Build on surfaces Zomato already has: offer creation, OTP consent, offer serving, weekly payout
  statement, Brand Packs for regulars. Why: the pitch is "plugs into the app", not a new product.
- D3. Uplift model and Qini are our own code (T-learner on sklearn HistGradientBoosting), no econml/causalml.
  Why: Python 3.14 wheels were missing, and own code is easier to explain to judges.
- D4. Prototype = FastAPI service with Zomato-style hooks + static partner-app screens (no JS build step)
  + simulator with ground truth. The public demo is a static export of the service's answers (GitHub Pages).
- D5. Keep the repo small and readable: 5 modules in `truelift/`, one static UI folder, 4 scripts, one
  pytest file. Do not add folders or frameworks without a clear need.
- D6. TrueLift keeps the owner's discount size. It chooses who sees the offer, the minimum order, the 3–6 pm
  slot and the Brand Pack (34 versions). Why: past offers vary size only between restaurants, so the size
  effect is weakly learned, and choosing the best of many noisy forecasts favours over-estimates (letting
  the model pick size cut profit to ₹6.48 L vs ₹7.65 L). Changing size needs a randomised depth test.
  Note (14 Nov, Kshitish): with the shadow phase exploring the create screen's sizes (M2), letting the model pick
  the size now raises own-offer profit (quick: ₹3.19 L -> ₹4.01 L) but not restaurants' market-wide profit
  (₹1.95 L -> ₹1.96 L), and losing offers rise 15 -> 38 (`reports/exp_depth_choice.json`). Size stays the owner's
  call for now; a per-restaurant 4-week depth test picks the better size only 61% of the time
  (`exp_depth_test.json`), so a size change needs pooled or longer tests. Team to re-decide after the final run.
- D7. Real restaurant names are shown (looks real), with "Simulated data" on every screen and doc.
  Customers are synthetic; no real customer data anywhere. (Yash, 13 Nov.)
- D8. Weekly measurement = restaurant's own 10% holdout combined with the model's prior by precision
  (empirical Bayes), plus regression adjustment (CUPED-style). Why: a holdout alone is too noisy for a
  ~50-orders-a-week restaurant; the adjustment cut noise 27%.
- D9. Headline metric is each offer's own effect (other restaurants unchanged): "offers that pay" and
  own-offer profit. Market-wide numbers are shown too but mix in competitors' offers.
- D10. Zomato co-funding is presented as a caution, not a feature: unmeasured co-funding cost ~₹5 L a week
  for ~70 extra orders in the simulator.
  Note (14 Nov, Kshitish): the ~₹5 L came from a simulator bug: Zomato's share was paid on every redemption,
  not only for customers new to Zomato (audit TL-003). Fixed on `kshitish`; in the quick configuration the
  co-funding cost falls about tenfold and Zomato's contribution turns positive. Re-read D10 after the final run.
- D11. Holdout assignment = stable hash of (customer, offer), 10%. Eligibility never uses device, payment
  method or inferred income (CCPA notices to ride-hailing apps over phone-based pricing, Jan 2025).
- D12. No AI attribution in git history or PRs; shared Claude context lives in `CLAUDE.md` + `.claude/context/`
  and is updated with every change. (Yash, 13 Nov.)
- D13. (Proposed for `main`; Kshitish, 14 Nov.) On branch `kshitish` the service is split into small modules
  (assignment, features, training, schemas, settings, store, state, observability, demo) and the tests into files
  by area plus golden, fuzz and browser suites. Supersedes D5 once the team agrees at merge time. Why: each audit
  fix needed a test that isolates one concern, and `api.py` mixed routes, state and simulation in 400+ lines.
- D14. Library versions are pinned in `uv.lock` (NumPy 2.2.6, pandas 3.0.5, scikit-learn 1.5.2, SciPy 1.14.1);
  Python 3.11 to 3.13; `requirements*.txt` are exported from the lock. Why: the committed numbers reproduce
  exactly with these versions (full pipeline re-run on 14 Nov equals `reports/` to 1e-6), and a pickled model
  loads only in the scikit-learn that wrote it. (Kshitish, 14 Nov.)
- D15. CI publishes the demo to `gh-pages` from `kshitish` only after lint, tests (Linux and Windows), golden
  numbers, fuzzing, browser tests (static and live) and the Docker check pass, and only for a commit marked
  `[deploy]` or a manual run. It refuses a site built without the committed model. Why: no untested or
  half-finished build reaches the public link. (Kshitish, 14 Nov.)
- D16. (Kshitish, 14 Nov.) TrueLift picks each offer for the restaurant's profit only (Zomato weight 0). Why: the
  frontier run (Zomato weight 0.5, 1, 2 on its contribution) gives Zomato no more commission or contribution
  while restaurant profit falls and losing offers rise (quick: 10 -> 19), because both sides earn from the same
  extra orders. The 60%-chance-of-profit floor applies at any weight. `Engine.best_design(zomato_weight=...)` stays
  for the analysis.
