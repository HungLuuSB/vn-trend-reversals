# Pre-freeze leakage audit, Paper 1 (2026-11-26)

D-024 gate 4. Scope: labels, risk set, feature blocks A–E, splits and fitting, warehouse timing,
the trading test and the snapshot. Two independent parts:

1. **Empirical tests.** Perturbation, timing validation and correlations.
2. **Code review.** A separate reviewer was given the code and the rules, but none of the findings from part 1.

No model was fitted or evaluated on the test years 2017–2026. Scripts and counts are below; the
fixes are in PRs #83 and #84.

## Results (fail first)

| Check | Status | Evidence | Fix / disposition |
|---|---|---|---|
| Block E `npl_change` timing | **fail → fixed** | Perturbation test: scrambling values public after a cutoff changed earlier features. `max()` skipped NaT, so a change involving a never-public quarter (EIB 2025 Q4) was dated by the other quarter alone. 65 EIB rows in the test years were affected. | `skipna=False`; test fails on the old code (D-023 clarification 10, PR #83) |
| Block E ties at the same `available_at` | **fail → fixed** | Same test: Q1 and Q2 2011 tie at the calendar start, and the join's pick depended on unrelated rows. 2011 rows only. | Latest quarter wins (D-023 cl. 10) |
| Final walk-forward runner | **fail (blocker, open)** | `walkforward.py` exits on `--final`. No code touches 2017–2026, so that code cannot be audited yet. | Write it from the audited dev pieces; test on synthetic data; audit that code before the one-shot run (D-025) |
| Block E and Paper 2 inputs outside the snapshot | **fail → fixed** | `add_block_e` and Paper 2 read `data/extracted/` and `data/staging/paper2/`. | `snapshot.freeze_derived` freezes them, drops rows after 2026-11-20 and hashes them into the snapshot id. The readers prefer the snapshot (`paths.frozen_input`). |
| Snapshot gate accepted a partial dbt run | **fail → fixed** | The last `run_results.json` was `build --select market_classification_events` with no look-ahead test in it. | `check_dbt_clean` requires a full unselected `dbt build` with passing `no_feature_after_decision_time` tests; tests added |
| Test-year label statistics printed | **fail (minor) → fixed; disclosed** | The labels runs' `summary.json` gave pooled 2012–2026 outcome statistics, e.g. reversal within 5 days on 0.263 of rows, and median durations. | `summarise` now reports outcomes for `trade_date <= dev_end` only. These pooled base rates were seen; no model performance on the test years was |
| Hard-coded design values | **fail (minor) → fixed** | Costs, τ grid, NPL margin, bootstrap block, study dates and decision hour were literals. | Moved to `main.yaml` and pinned in `test_config.py`, including the SQL study window |
| Purge drops rows instead of censoring them at the fold boundary | **fail (minor) → kept as pre-registered; disclosed** | Training rows whose swing ends at or after the fold start are dropped, so kept rows near the boundary lean towards short swings. 2016 fold: 79 rows; P(dur≤5) 0.255 kept vs 0.245 all. No test information is used. | D-025: keep the pre-registered purge; report censoring at the boundary as a sensitivity in the final run |
| HBB (Habubank) prices | **fail (minor) → disclosed** | The only bank delisted in the study period; it is in neither CafeF source (D-006, `known_price_gaps`). 155 sessions in 2012. | Disclose in the data section |
| Block E publication timing (undated statements) | **unknown → pass** | D-023 pre-registered news check (`block_e_timing.py`). Result news is earlier than `available_at` for 878/879 dated statements (median lead 34.9 days) and 179/179 undated ones (37.7 days). The exception (BAB 2025 Q2) is dated, and its only matching article is 72 days late. | – |
| Block E publication timing (late filers in general) | **residual risk** | The legal deadline + 5 sessions is the bound. CafeF's upload timestamps are re-uploads, not first publication. | The pre-registered margin-20 robustness check; disclose |
| "First release" of block E files | **unknown → disclosed** | The earliest creation date among files CafeF lists now. A silently replaced original cannot be detected. | Disclose |
| GPR vintage | **unknown → disclosed** | One download (2026-11-24) is used for all history. The daily GPR was not published in real time before about 2021. The publication lag is conservative (at least 4 days). | Disclose (pseudo-real-time, as is usual for this index) |
| Bootstrap block length | **unknown → sensitivity** | Block 20 sessions; swing durations: median 11, p75 21, p90 34. | D-025: blocks of 40 and 60 reported as sensitivity |
| Shuffled-label control for ABCDx / nn | **unknown → final runner** | Pre-registered for logit ABCD and nn_seq_ABCD in dev; ABCDx had only a diagnostic (0.500). | D-025: the final runner runs it for every reported model |
| News text | **unknown (minor) → disclosed** | Crawled in 2026; times from CafeF `pdate`; later edits cannot be detected. | Disclose |
| Backtest details | **unknown (minor) → disclosed** | A stock without a trade drops out of that day's mean, and its gap return is booked on its next trading day. No capacity limit. UPCoM fills (pre-registered sensitivity). | Disclose |
| Blocks A/B, sequences, VN-Index state | **pass** | Price perturbation (`perturb.py`): every price and volume after the cutoff scrambled, at 5 cutoffs (2013–2025) for 60 random stocks. 224 series and 369,855 rows bit-identical; the positive control changed. The reviewer's truncation checks agree. | – |
| Block E and news after the fixes | **pass** | Perturbation (`perturb_e.py`): 5 cutoffs × 105,560 bank-session rows unchanged. News with all later articles deleted: 3 cutoffs unchanged (7,256 / 16,848 / 25,472 rows). | – |
| Join keys (t vs decision date) | **pass** | `decision_date` is the next HOSE session on 100% of rows. Local market `source_session` = t; global data joined on the decision date; NPL as-of strictly before 09:00; the news window ends at the decision date (asserted). | – |
| Time zones, DST, Asian markets, holidays | **pass** | Exchange-local `obs_date`. HSI/SSE lag ≥ 1 day. SPX available 20:00 UTC in summer, 21:00 in winter. Changes between consecutive decision-time values (data rule 8). | – |
| Development splits and fitting | **pass** | Chronological, expanding; purge; 20-session embargo; imputers and scalers fitted on training rows; tuning on the inner year; no data-driven selection. | – |
| Labels and risk set | **pass** | θ from t−1 ATR and close; no whole-sample statistics; the 250-day rule is point-in-time; censoring at 2026-11-20 is correct. | – |
| Point-in-time universe; adjusted vs raw prices | **pass** | VN30 spells by effective date. Limit flags and fills use raw prices; adjusted prices only for ratios. | – |
| Feature–target correlation (dev rows) | **pass** | Only `swing_dist` (Spearman −0.26), which is mechanical (D-016 baseline); all others ≤ 0.07 in absolute value. | – |
| Duplicates | **pass** | 0 duplicate (ticker, trade_date) in 139,241 rows. | – |
| Backtest timing, settlement, costs | **pass** | Signal at the close, fill at the next open; no sell at limit-down; T+3/T+2 from the seed; 0.15% + 0.25%. | – |
| Paper 2 large-shock threshold | **pass** | `large_shocks` uses only US days mapped to sessions ≤ 2026-11-20, although the GPR file runs to 2026-11-23. | – |

## Verdict

- No look-ahead remains in the code that builds labels and features. The one real leak (block E `npl_change`) was in test-year rows only and was fixed before any test-year run.
- **The freeze can go ahead** once PR #84 is merged and a full `dbt build` passes.
- **The final run cannot go ahead yet:** its runner does not exist. It must be written from the audited development code, tested on synthetic data, and audited itself before the user's go-ahead.
