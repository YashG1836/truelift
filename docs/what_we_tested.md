# What we tested, what we found, and what is still not right

After the Round 2 submission we audited our own work the way a sceptical reviewer would: every
source file read against every claim made about it. That produced 50 findings (TL-001 to TL-050).
This page shows the six that mattered most, how each was found, what fixed it and which test now
guards it, then the other findings in groups, then what is still not right. The numbers each fix
moved are in the corrections table of `DEVLOG.md`, with before and after.

## The six that mattered most

**1. Serving and measurement held out different customers (TL-004).** *Found by* reading the two
code paths side by side: the page's "control group" and the weekly measurement each drew their own
random customers. A measurement of customers who did see the offer would have looked like no effect.
*Fix:* one hashed assignment of (customer, offer) in `truelift/assignment.py`, used by serving, the
customer panel, the simulated weeks and the measurement. *Guards:*
`test_serve_and_measurement_share_holdout`, `test_holdout_is_stable_across_weeks`,
`test_offer_ids_switch_the_simulator_to_the_shared_assignment`.

**2. Concurrent quotes could read each other's predictions (TL-001).** *Found by* reading the quote
cache: one dictionary shared by every request, keyed without the restaurant. Two owners quoting at
once could see each other's forecast. *Fix:* a cache that lives only for one quote, passed down
explicitly, with a size check that fails loudly on misuse; serving never touches it. *Guards:*
`test_concurrent_quotes_match_sequential` (eight threads), `test_prediction_cache_rejects_misuse`,
`test_serve_never_calls_the_model`.

**3. The simulator paid Zomato's co-funding on every redemption (TL-003).** *Found when* Zomato's
side of the ledger did not add up with what the documents said Zomato would fund, so unmeasured
co-funding looked far more expensive than it is. *Fix:* co-funding only for customers new to
Zomato, in the simulator exactly as in the engine. *Guards:* `test_cofunding_only_for_new_to_zomato`,
`test_engine_and_simulator_agree_on_funding`, `test_unmeasured_cofunding_moves_money_without_creating_orders`.

**4. Forecasts were too low (TL-006, TL-007).** *Found by* a new check of the forecast against the
truth, which the pipeline had never made: forecasts were well below the truth, for blanket offers
most of all, and the misses were all on the cautious side. Three causes: the quote read features
computed after the visits it was forecasting, so its customers looked more loyal than future
visitors; training and serving computed the look-back windows differently; and the shadow phase
explored discount sizes of ₹40 to ₹100, while owners' offers are 10% to 25% of their order, which
tree models cannot extrapolate to. *Fix:* point-in-time features, one feature definition with fixed
windows, a shadow phase that explores the create screen's own options, and a skew check and a drift
report that fail the pipeline if the windows ever diverge again. *Guards:*
`test_features_depend_only_on_lookback`, `test_quote_population_has_no_lookahead`,
`test_no_training_serving_skew`, `test_drift_report_fails_when_the_old_window_fault_returns`,
`test_forecast_is_centred_on_the_truth_in_todays_market`.

**5. Offers were paused on noise (TL-009, TL-017).** *Found by* an A/A test: placebo offers that
change nothing were paused by the old rule ("pause when the range is below zero"), more often the
more weeks an owner looked. *Fix:* a pause needs the offer's own control group to show a loss beyond
an always-valid boundary, with at least 30 held-out customers; the model alone can only warn
("probably losing"); both noise sizes are re-estimated every week across running offers. *Guards:*
`test_false_pause_rate_under_null`, `test_pause_needs_its_own_evidence_and_a_real_control_group`,
`test_confidence_sequence_is_wider_than_a_fixed_interval_and_never_shrinks_below_it`,
`test_zero_order_control_group_does_not_look_certain`, `test_weekly_ranges_cover_the_truth_near_the_stated_rate`.

**6. The best of 34 forecasts flattered itself (TL-018).** *Found by* comparing, for every restaurant,
the suggested version's stated advantage over the owner's offer with its true advantage. *Fix:*
predicted gains calibrated on the shadow phase's holdouts (above and below zero separately), a
version offered only with at least a 60% chance of making money, and the range shown with every
suggestion. *Guards:* `test_chosen_version_usually_beats_the_owners_and_its_advantage_is_not_inflated`,
`test_gain_calibration_scales_each_side_and_keeps_signs`, `test_no_offer_is_chosen_when_every_version_loses`.
This one is only partly fixed; see the last section.

## The other findings, in groups

| Findings | What was wrong | Guard |
|---|---|---|
| TL-002 | The published demo asked for design files that were never exported | `scripts/export_static.py` stops when a file the page can request is missing; `test_static_export_keys_match_the_page` |
| TL-005, TL-013, TL-014, TL-036 | Latency was timed on the wrong path and read from a shared list; the restaurant list recomputed the order matrix for every card; start-up rebuilt history on the first request | `test_serve_never_calls_the_model`, `test_restaurants_endpoint_is_fast_and_carries_design_options`, `test_card_values_match_the_raw_history`; latency timed end to end over HTTP by `scripts/bench_latency.py` |
| TL-008, TL-024, TL-037 | All visitors shared one state; a restaurant could run several offers at once, each measured as if alone; a double click could run a week twice | `test_sessions_are_isolated`, `test_one_active_offer_per_restaurant`, `test_run_week_concurrent_calls_append_once`, `test_idempotency_key_on_approve` |
| TL-010, TL-042 | Market-level results were missing; "new to Zomato" also caught dormant customers | `test_frontier_and_control_set_are_reported`, `test_new_to_zomato_matches_first_order` |
| TL-011 | Sample customers were always shown at dinner, so a 3–6 pm offer showed nobody | `test_offpeak_sample_customers_use_offpeak_slot` |
| TL-012, TL-038 | Impossible designs were accepted or crashed; every value was rounded to three decimals | `test_invalid_inputs_return_problem_details`, `test_clean_preserves_small_values`, `test_contract_holds_for_any_input` (fuzzing) |
| TL-015, TL-021, TL-044 | A fresh clone could not start the service; dependencies were unpinned; the model file was loaded unchecked | `uv.lock`; `test_missing_model_returns_503_with_instructions`, `test_model_hash_mismatch_is_refused`, `test_model_trained_on_other_inputs_is_refused_at_load` |
| TL-016 | The Brand Pack reward was neither randomised nor measured on its own | `test_brand_pack_has_its_own_control_group`, `test_brand_pack_line_recovers_a_known_effect` |
| TL-019, TL-029 | The no-offer model learned mostly from customers who were not randomly held out; standard errors treated a customer's repeat visits as independent | `test_frontier_and_control_set_are_reported` (the held-out-only variant is reported), `test_noise_scale_from_split_halves` |
| TL-020 | The value of topping up to a minimum order was fitted on the wrong unit | `test_topup_value_recovers_truth`, `test_topup_fit_recovers_a_known_value_from_visit_counts` |
| TL-025, TL-028 | The OTP and the consent record were demo-grade; serving decisions were not logged, so the measurement read simulator rows | `test_otp_attempt_limit`, `test_otp_expiry`, `test_consent_record_verifies_and_detects_tampering`, `test_measurement_from_log_equals_measurement_from_rows` |
| TL-030, TL-031, TL-032 | "No offer" showed a ±₹3 range; "same discount size" could appear when the suggestion had none; the WhatsApp summary offered replies that did nothing | `test_no_offer_quote_has_zero_range`, `test_weekly_message_uses_one_money_format_and_says_what_to_do` |
| TL-033, TL-035 | The page kept its own copy of constants; the serving fallback silently showed a targeted discount to everyone | `test_payout_uses_terms`, `test_config_shares_the_constants_the_page_needs`, `test_decision_table_falls_back_to_the_owners_rule_and_says_so`, `test_fallback_counter_stays_zero_after_a_normal_flow` |
| TL-039, TL-040 | The Qini figure used a private normalisation; the real-data check had no baseline and no interval | `test_measures_match_a_hand_computed_case`, `test_library_qini_is_one_for_a_perfect_ranking_and_absent_for_money` |
| TL-022, TL-023, TL-043, TL-046, TL-047, TL-048 | The static demo showed the export time as the moment of approval; the guided demo could be left half-done and had no Back; accessibility gaps; fonts loaded from Google; failed loads were reported as missing designs | Browser tests in `tests/ui/`: the guided demo to Finish, every tab, a manual offer, no broken text, no sideways scrolling at 390 px, and the offline runs block every other host |
| TL-026, TL-027, TL-050 | Five published numbers had no script behind them; the README, the plan and the code disagreed; a docstring named an output that was not written | `scripts/check_claims.py`, `scripts/render_tables.py --check`, `test_committed_openapi_contract_is_current` |
| TL-034, TL-041, TL-045, TL-049 | Commands that worked only on Linux and macOS; the simulator silently assumed equal localities and contiguous ids; hygiene; no licence | `tasks.py` and CI on Linux and Windows; `test_market_rejects_unbalanced_localities`, `test_market_rejects_gaps_in_restaurant_ids`; ruff and pyright in CI; `LICENSE` and `NOTICE` |

## What is still not right

- **The suggested version is oversold.** Its stated advantage over the owner's offer is still several
  times its true advantage, although most suggestions truly are better. The page shows the range and
  says the gain may be smaller; a fix needs more shadow-phase data per restaurant.
- **The weekly estimate inherits a bias from the model.** Across ten random holdout draws, the
  four-week estimate over-states the truth by a few hundred rupees an offer on average, more than its
  standard error. Its ranges still hold the truth near their stated rate. Weighting the offer's own
  control group more as weeks pass reduces it; removing it needs a less biased prior.
- **Blanket offers are under-forecast.** For owners' blanket offers the quotes add up to about two
  thirds of the true effect (TrueLift's versions are closer). The owner sees a cautious number.
- **On real data the simple shortcut wins somewhere.** On Criteo's rare purchases, ranking people by how
  likely they are to buy beats TrueLift's T-learner; the X-learner comes close. This is reported, not
  hidden, and the shadow phase is where Zomato would choose between them.
- **The simulator has no dynamics.** Habits, competitors' responses and capacity do not change over the
  weeks; the sensitivity sweep and the moving-history variant are the only checks of that.

The exact values behind these statements are in `reports/` and in `docs/method_and_evidence.md`,
where the claims ledger (`docs/claims.yml`) checks them against the reports.
