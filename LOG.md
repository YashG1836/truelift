# TrueLift Round 2: working log

Read this first when resuming. It records what is done, what was decided, why, and what comes next.
Newest entries at the bottom of each section. Paths are relative to `Eternal_hack/`.

## Context
- Team "Team - Banana" (Yash Goyal, Bhavay Goyal, Kshitish Madbhavi), IITGN × Eternal hackathon.
- Round 1 submitted: `TrueLift_Problem_Statement_Draft16.pdf` (title on Eternal's list: "TrueLift: Smarter Discount Optimisation for Food Delivery").
- Shortlisted: 10 teams. The other 9 are operations topics: Inventory Truth (shelf checks), ChargeAware (EV battery swaps), DropPoint (delivery end points), FirstStock (new Blinkit dark stores), OneSwap (Hyperpure SKU swaps), ShelfLife (Blinkit expiry), ASCI (demand during stockouts), Eternal Lite (offline order relay), FAIR (support resolution auditing). TrueLift is the only marketplace / restaurant-economics / pricing problem.
- User's Round 2 asks (12 Nov 2026): be the best of 10; be specific to the problem; research with no mistakes; show calculations fully (no page limit now); build an end-to-end prototype that could plug into the Zomato app; keep this log.
- Kept drafts (user's choice): 1, 7, 8, 15, 16 (PDFs in project root). Read on 12 Nov.

## Verified research (12 Nov 2026)
Each line: fact → source → how verified.
1. Zomato agreed restaurant-funded campaigns become opt-in, approved by OTP before a promotion starts; past deductions examined outlet by outlet. Swiggy agreed to seek consent and refund. → Angel One, 8 Aug 2026 → read page text.
2. Bengaluru Hotels Association also wants consent valid only for an agreed period, fresh approval for extensions, itemised payouts. → Angel One / The Week / inkl (Jul–Aug 2026) → search summaries. No reporting found on what happened after the 1 Sep deadline. Status of OTP rollout = open question for Eternal.
3. Eternal Q2 FY27 (quarter to Sep 2026), food delivery: NOV ₹11,445 Cr (+21.5% YoY, 5th quarter of acceleration); adjusted EBITDA ₹627 Cr = 5.5% of NOV; MTC 28.0M. → Eternal Q2 FY27 shareholder letter PDF (read text).
4. Active restaurant partners 334,000 (Q2 FY27), up from 328,000 in Q1. → MediaNama Q2 article (read text). Not in letter text I extracted.
5. Eternal consolidated "Advertisement and sales promotion" ₹1,138 Cr in Q2 FY27 vs ₹945 Cr Q1 FY27 vs ₹806 Cr Q2 FY26 (+41% YoY). → results table in the Q2 letter PDF (read). Consolidated, not food-delivery only.
6. Eternal leadership on discount-acquired customers (Albinder, Q2 letter, about Blinkit): "A customer who shows up only for a deep discount uses the same capacity as one who orders every week… those customers usually leave when the discount ends." → letter text.
7. Q2 letter: "over 65% of Zomato app opens are exploratory… users browse an average of 12 menus and over 100 food images before ordering." → letter text. Supports the ATC angle (undecided browsers are where a discount can change the decision).
8. Swiggy Q2 FY27: ~100 bps of GOV into "targeted investments… prices tailored to particular customer groups, to win back lapsed users" (Instamart). Discounting is back. → Business Today, 26 Oct 2026 (read text).
9. Swiggy "Discount Self Serve" (Apr 2024): restaurants configure discounts, target customer segments, track performance; ~1 lakh restaurants. → Swiggy blog (read text). Targeting + redemption tracking already exist; causal measurement is not mentioned.
10. Zomato "Brand Packs" (Jul 2024): restaurant loyalty feature rewarding repeat orders, 4,000+ restaurants at launch. → Business Standard (read text). Use as the regulars lever instead of inventing one.
11. Zomato shares customer phone numbers with restaurants only after customer opt-in (2025). → Inc42 / Outlook Business (search summaries).
12. CCPA (consumer authority) sent notices to Ola/Uber in Jan 2025 over alleged phone-based differential pricing; minister said food delivery would be looked at. → Business Standard / Autocar Pro (search). Design rule: eligibility never based on device, payment method or inferred income.
13. CCI price-parity / exclusivity case still pending as of Jul 2026 (NRAI sought interim relief). → Business Standard, 15 Jul 2026 (search).
14. Ownly: >50,000 orders/day in Bengaluru (~10% of 5–6 lakh/day market) by Aug 2026; Hyderabad launch Sep 2026. → Angel One/Moneycontrol, ThePrint (search).
15. MT-LIFT (Meituan): ~5.54M rows, 99 anonymised features, randomised coupons (control + 4 treatment arms), labels = click and conversion only (no spend/GMV). → GitHub README (read) + FunnelCausalNet arXiv 2608.11675 (search). Consequence: real-data validation can prove targeting (who converts because of a coupon) but not rupee profit; profit is shown in the simulator.
16. Commission base (pre- vs post-discount) differs across third-party calculators (Petpooja vs others). → search. Make it a simulator parameter; ask Eternal.
17. DoorDash (Dec 2025 blog) moved from blanket coupons to causal ML because coupons "worked — but at a high cost, often without knowing which users were truly influenced". → search summary only; page returned 403. Cite carefully.

## Key analysis results
- Example (unchanged from Draft 16, rechecked by script): per ₹400 order restaurant keeps ₹132, Zomato ₹100; with ₹60 off ₹90 / ₹85. Today if approved: restaurant −₹240/week, Zomato +₹1,500. TrueLift: restaurant +₹2,050, Zomato +₹2,550. Discount per extra order: ₹200 today vs ₹82 with TrueLift.
- Holdout precision (assumed 1,000 eligible visitors/week, 7% → 10% order rate, i.e. +3 pts): 10% holdout, 1 week → 95% CI ±5.4 pts (cannot tell); 4 weeks → ±2.7; 20% holdout 4 weeks → ±2.1; pooled across 50 similar outlets, 1 week → ±0.8. Conclusion: a small restaurant's own holdout is too small alone; estimate = pooled uplift model, corrected by the restaurant's own holdout over time, always shown as a range. This refines Round 1's "comparing the two groups shows the real extra orders".

## Simulator calibration (12 Nov, after tuning price sensitivity to 0.45/1.2/2.6/1.6 and AOV = 0.7 × cost for two)
- Per occasion, Zomato order probability: loyal 0.67, casual 0.41, deal_seeker 0.12, infrequent 0.30; Swiggy 0.09/0.26/0.63/0.24.
- No offer: 15,838 orders/week across 300 restaurants (52.8 each), AOV ₹460.
- Blanket ₹60 everywhere: 34% of redemptions are extra orders for that restaurant; only 18% are extra for Zomato (rest moved between restaurants). Restaurant profit −6.4% market-wide; Zomato commission +12%.
- One restaurant in ten runs blanket ₹60: median restaurant +₹213/week, 25% lose more than ₹557/week → owners can't tell which group they are in (the problem).
- Loyal customers are 53% of blanket redemptions but only 16% of them are extra orders. Observable regulars (3+ orders in 4 weeks) = 3% of menu visits, 21% of orders.
- MT-LIFT README for comparison: control conversion ≈3.1%, coupon ≈8.3% → ~63% of coupon conversions incremental (targeted coupon pushes, not blanket restaurant offers).
- MT-LIFT download needs a Google sign-in now (automated download fails). Ask the user to download train.csv/test.csv manually into `data/raw/mt_lift/`.

## Decisions
- D1. Scope stays restaurant discount optimisation on Zomato food delivery. No Blinkit/District/cancellations.
- D2. Build on existing Zomato surfaces: offer creation + OTP consent, offer serving, weekly payout statement, Brand Packs for regulars.
- D3. Implement uplift learners (T-/X-learner on sklearn HistGradientBoosting) and Qini/AUUC ourselves. Reason: Python 3.14 here, econml/causalml may lack wheels; own code is also easier to explain.
- D5. Repo kept small (user, 12 Nov): 5 modules in `truelift/` (economics, sim, model, engine, api) + `static/` UI, `scripts/` (build_restaurants, run_pipeline), one tests file, `reports/`, README.
- D4. Prototype = Python service (FastAPI) exposing Zomato-style hooks + mobile-width partner-app screens served as static files (no JS build step), + a simulator with ground truth, + evaluation report.

## Plan / status
- [x] Read 5 kept drafts
- [x] Research pass 1 (above)
- [ ] Write `round2/TrueLift_Round2_Plan.md` (problem, gap, method, all calculations, validation, demo, questions for Eternal)
- [x] Set up venv `round2/.venv` (Python 3.14; fastapi, sklearn, pandas, numpy, scipy, pytest). Install: `pip install -r requirements.txt`
- [x] Restaurant seed: `scripts/build_restaurants.py` → `data/processed/restaurants.csv` (300 delivery restaurants, 6 localities × 50, from Kaggle Zomato Bangalore 2019 via GitHub mirror mohammadn0man/Zomato_bangalore_restaurant_opening_prediction; raw zip in `data/raw/zomato_blr/`)
- [x] Money model `truelift/economics.py` (exact 29.5% commission+GST; example → today restaurant −₹210, Zomato +₹1,500; TrueLift +₹2,101 / +₹2,550; Round 1 used rounded 30% → −₹240 / +₹2,050)
- [x] Simulator `truelift/sim.py` (logit choice among 8 menus + Swiggy + nothing; hidden types loyal/casual/deal_seeker/infrequent; exact counterfactual per exposure; hashed holdout; history = 4 weeks status quo + 4 weeks shadow phase with random designs and 10% holdout → ~1M training rows)
- [x] Uplift model `truelift/model.py` (T-learner on sklearn HistGradientBoosting; Qini). Check vs truth: predicted-uplift deciles track true uplift (top decile 0.093 vs 0.087), Qini 0.24 vs random 0.01; "new to restaurant first" heuristic −0.02 (worse than random).
- [x] Engine `truelift/engine.py`: quote (forecast + range), design search (131 designs), targeted serving (show iff expected profit gain > 0), measurement (own holdout combined with model prior by precision weighting), auto-pause, WhatsApp text, calibration (empirical Bayes, cross-fitted).
- [x] Pipeline `scripts/run_pipeline.py` → `data/processed/model.pkl`, `reports/evaluation.json`, `reports/restaurants_results.csv`, `reports/measurement_check.csv`.
- [x] API `truelift/api.py` (FastAPI; hooks quote / offers / approve (OTP) / serve / run_week / decision / customers / evidence / example) + UI `truelift/static/` (index.html, app.js, style.css): phone screens (home, create with live forecast + better version, OTP consent, weekly results with report-vs-TrueLift, WhatsApp, itemised payout), "Inside Zomato" panel (who sees the discount, simulator truth, hook call log), Evidence tab, Money maths tab.
- [x] Tests `tests/test_truelift.py` (money maths exact, simulator truth consistency, holdout hash, audience rules, quote arithmetic, measurement recovers known effect, API end-to-end).
- [x] Final pipeline (23:00, after D6 + regression adjustment): TrueLift beats blanket and the rule on paying offers (242 vs 130 vs 211), own-offer profit (₹7.65L vs ₹6.94L vs ₹7.34L), market restaurant profit (+₹4.85L vs +₹2.46L vs +₹3.96L), discount given (₹10.0L vs ₹16.7L vs ₹10.8L), AOV (₹542 vs ₹533 vs ₹521); Zomato commission +₹6.38L vs +₹6.45L vs +₹5.95L. Plan §6 filled.
- [x] Static mode in app.js (window.TRUELIFT_STATIC) + `scripts/export_static.py 142 283 97` (parallel, ~3 min) → `site/`
- [x] Round 2 plan `TrueLift_Round2_Plan.md` (research table, money maths + break-even table, gap, four hooks with formulas, precision table, evidence, research plan, demo script, judge Q&A, questions for Eternal, limits, sources)
- [x] README, `scripts/validate_mtlift.py` (tested on a fake MT-LIFT-shaped file; real data needs manual download)
- [x] UI checked with Playwright screenshots (scratchpad `pw/flow.js`): create → better version → OTP (wrong OTP rejected) → 4 weeks → evidence → money → mobile. Fixed: reason capitalisation, chart labels, number wrapping, paise on money page, mobile header.
- [x] GitHub: private repo https://github.com/YashG1836/truelift (code, branch main); Pages from branch gh-pages (built site only; Pages URL is public, code stays private): https://yashg1836.github.io/truelift/ . Re-publish: run export_static, then in site/: git init -b gh-pages, commit, force-push to gh-pages.
- [x] Collaborators invited (push access): ksawesome, BhavayGoyal

## Findings while building (12 Nov)
- F1. First full run: TrueLift lost to the simple "new customers only" rule on total own-offer profit (₹6.46L vs ₹7.34L/week), though more of its offers paid (222/300 vs 211). Isolated test with a fixed design (15% off, no minimum): all model targeting variants beat blanket and the rule (₹4.75–4.80L vs ₹4.12L; oracle ₹5.17L), so targeting itself works; the loss came from design search.
- F2. Cause 1: restaurant "usual basket" was estimated from full-price orders that included customers who skipped a minimum-order offer (small baskets) → biased low. Fixed: use orders from customers not shown an offer (`restaurant_baskets`).
- F3. Cause 2: engine assumed every shown order uses a minimum-order offer. Data: use rate falls from ~97% (minimum ≈ 1.0× AOV) to 40–60% (1.3×). Fixed: `offer_mix` + `fit_topup_value` learns how much customers value a top-up from past offers (learned 0.525; simulator's hidden truth 0.50).
- F4. Market-wide, restaurants without offers lose orders to those with offers, so "restaurants worse off vs no offers" mixes in competitors' effects; headline metric = each offer's own effect (others unchanged): offers that pay, own-offer profit.
- F5. Naive Zomato co-funding (50% of discount for customers new to Zomato, unmeasured) cost Zomato ~₹5L/week for ~60 extra orders in the full run → Zomato's own discount money needs the same measurement; presented as a caution, not a feature.
- F6. Measurement: combined estimate beats own-holdout-only every week (MAE ₹1,060 vs ₹1,909 after 1 week); 80% ranges covered truth 69–77% (slightly narrow). Added calibration on targeted subsets (errors grow on selected customers) and decision metrics (keep / pause / wait precision).
- F8. After F2/F3 fixes TrueLift still trailed the rule (₹6.48L vs ₹7.34L own-offer profit). Variant test (full market, 10% holdout for all variants): targeted at the owner's 15% depth, no minimum = ₹7.75L, 234/300 pay, Zomato commission +₹6.34L; rule (same holdout) ₹6.81L; letting the model choose depth = ₹6.48L. Fixed depth + minimum-order search = ₹7.65L, 242 pay, highest market-wide restaurant profit (+₹4.86L) and Zomato commission (+₹6.38L). Cause: depth response varies only across restaurant-weeks in the shadow data → weakly learned; picking the best of many noisy forecasts favours overestimates. DECISION D6: TrueLift keeps the owner's discount size; it chooses who sees it, minimum order, 3–6 pm, Brand Pack (34 versions). Depth changes need a customer-level randomised depth test (next step).
- F9. Demo restaurant estimate looked biased (own-holdout high, model low). Tests: hash assignments independent across restaurants (|corr| 0.005); across 10 holdout draws mean error ≈ 0 → noise, not bias. Every pipeline run reuses the same weeks and holdout draw (common random numbers), so one draw's noise looked systematic. Added regression adjustment (subtract each visit's predicted no-offer outcome; CUPED-style): noise −27%, coverage 67% → 79% → 81% (weeks 1/2/4), keep-verdict precision 87/90/92%.
- F10. Public demo must not pin simulated profits on real restaurants: UI shows "Cuisine #id" (real listing attributes, no names); evidence JSON for the site has names stripped. `reports/restaurants_results.csv` (internal, private repo) keeps names.
- F7. Brand Pack rarely chosen (2/300): in this simulator rewarding regulars seldom pays, because loyal customers are not very price sensitive. Shown honestly; it depends on how price-sensitive regulars really are (ask Eternal for Brand Pack results).

## Next steps (as of 12 Nov, 23:30)
1. Download MT-LIFT by hand (Google sign-in) into `data/raw/mt_lift/`, run `scripts/validate_mtlift.py`, add the Qini per coupon arm to plan §6.
2. Owner interviews near campus (plan §7): screenshots of offer report, OTP screen, payout statement (commission before or after discount?).
3. Send Eternal the questions in plan §10 when mentors are assigned.
4. Rehearse the 5-minute demo (plan §8) on the live site; keep the local server as backup (`uvicorn truelift.api:app`).
5. If time allows: customer-level depth test (two discount sizes at random) and a platform-level holdout for Zomato-funded discounts.

## Session notes
- 12 Nov: user asked: keep repo small and easy to read; host demo on GitHub Pages if it's a website; 'be smart, do everything properly end to end'.
- 12 Nov: downloads kept in scratchpad `dl_r2/` (Q2 letter PDF, articles). Scratchpad is session-only; facts needed later are copied into this log.
