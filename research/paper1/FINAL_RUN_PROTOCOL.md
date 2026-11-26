# Paper 1 final run: protocol (D-026)

**Amended by D-027 (2026-11-26, before any test-year output):** mechanical nulls `M_flex` and `RW`, spline H3, year-stratified primary metrics, the stricter H5 rule, named primary tests with 1,000 resamples, the H2 sign test, the RQ4 single-index primary, an upper-side-only shuffled stop. Where this file and D-027 differ, D-027 wins.

**Status:** approved by the user on 2026-11-26: the RQ4 design (5a), execution at the close (5b), and vast.ai for compute (section 7, option 2). Written before any test-year output exists. Nothing in it may change after the run starts. Sections 1–6 collect what D-012 to D-025 already pre-registered; the items marked **NEW** were the open ones.

## 1. Data and folds

- **Input.** One frozen snapshot (D-024), labels and features rebuilt from it, block E read from it.
- **Test years:** 2017, …, 2026. Each year is a fold:
  - training data: every row from 2012 up to the year's start, minus the purge (rows whose swing ends on or after 1 January) and the embargo (the 20 sessions before it);
  - refit each January;
  - 2026 ends at the 2026-11-20 close, and open swings are censored there.
- **Tuning** (D-014): nested. The inner validation year is the last full year before the test year, with the same purge and embargo. Hyperparameters are chosen by the lowest inner IBS on the D-014 / D-022 grids, then refitted on the full training data.
- **Specification lock:** every feature list, grid and decision rule below is the one used in development.

## 2. Models and feature sets (each tuned once per year; predictions cached)

| Family | Specifications |
|---|---|
| Kaplan–Meier | no features |
| Logistic hazard (landmark, D-013) | `M`, `DIST`, `AGE` (D-016, D-019); `ABC`, `ABCD` (D-014 additive); `ABCx`, `ABCDx`, `MBCx`, `MBCDx` (D-017; `ABCDx` is the **main specification**); `ABCDx_bank` (D-020) |
| Cox (ridge) | `ABCx`, `ABCDx` |
| Gradient-boosted hazard | `ABC`, `ABCD` (raw; D-017 tree check) |
| Random survival forest | `ABC`, `ABCD` (raw) |
| Neural (D-022) | `nn_seq_ABCD`, `nn_seq_ABC`, `nn_static_ABCD`; outer refits average seeds 0, 1, 2 |
| Bank rows only (D-023) | `M`, `M+E`, `ABCDx`, `ABCDx+E` |

- **Leave-one-out (D-018):** the 14 block-D features dropped one at a time from `ABCDx`, plus the gold/GPR pair. These use `ABCDx`'s hyperparameters for the year, with no re-tuning.
- **Shuffled-label controls** (D-013, D-025): `ABCD` (10 seeds), `ABCDx` and `M` (10 seeds each), `nn_seq_ABCD` (3 seeds). A pooled C-index above `too_good_c` = 0.70 for any model **stops the run** for a leakage audit.

## 3. Metrics and inference

- **Per year and pooled over the 10 years:**
  - Uno's C (τ = 20);
  - IPCW integrated Brier score (days 1–20);
  - time-dependent AUC at 5, 10 and 20 days;
  - calibration at 5, 10 and 20 days (deciles).
- **Paired differences:**
  - moving-block bootstrap over test dates, blocks of 20 sessions and 200 resamples, the same resamples for every model;
  - 95% percentile intervals;
  - Diebold–Mariano tests on the daily mean Brier loss at 5 days, with Newey–West errors (proposal).
- **D-025 sensitivities** (reported next to the main results, never replacing them):
  - bootstrap blocks of 40 and 60;
  - the main comparisons refitted with censoring at the fold boundary instead of the purge.

## 4. Confirmatory tests and decision rules (as pre-registered)

An improvement counts only if the pooled C interval is above zero **and** the pooled IBS interval is below zero (D-016 to D-023 rule).

| Question | Test |
|---|---|
| **RQ1 / H1** | Every model − KM. Main: `ABCDx` − KM. **Beyond the mechanics (D-016):** `ABCx` − `M`, `ABCDx` − `M`, `nn_seq_ABCD` − `M` |
| **RQ2 / H2** | Primary: `ABCDx` − `ABCx`. Also `MBCDx` − `MBCx`; per family, D vs no D (Cox, GBM, RSF, `nn_seq_ABCD` − `nn_seq_ABC`). The directional part of H2 uses the signs of `spx_ret_xdir`, `nasdaq_ret_xdir` and `vix_chg_xdir` in the yearly `ABCDx` fits (coefficients reported per year). Bank part: `ABCDx_bank` − `ABCDx` (D-020). Attribution: D-018 leave-one-out (IBS, 2,000 resamples, Holm across 14), gold vs GPR |
| **RQ3 / H3** | `M` − `DIST` (primary), `AGE` − KM, `DIST` − KM; the D-019 descriptive shape table on test rows |
| **RQ4 / H4** | **NEW**, see section 5 |
| **RQ5 / H5** | D-021 trading test on 2017–2026 exactly as in development: model exit (`ABCDx`), mechanical exit (`M`), DC exit, buy-and-hold. τ is chosen each year on the inner year. Costs 0.4%, with 0.2% and 0.8% as sensitivities. Sensitivities for unknown limits and close-at-floor. Deflated Sharpe ratio with N = 16; paired block bootstrap of Sharpe differences |
| **Block E (D-023)** | Bank rows: `ABCDx+E` − `ABCDx` (primary), `M+E` − `M`. Robustness: OCR values only; margins of 0 and 20 sessions; all news aliases |
| **Neural (D-022)** | `nn_seq_ABCD` − `nn_static_ABCD`, − `ABCDx`, − `M`, − `nn_seq_ABC` |

## 5. Items the decisions left open (NEW; approved 2026-11-26)

**5a. RQ4: has sensitivity to global shocks risen since the FTSE announcement?** RQ4 is exploratory in the proposal. Only the 2026 refit has any post-announcement training data (about 2.5 months), so an out-of-sample test has almost no power. Proposed instead: an estimation on the full sample, which also says plainly that RQ4 is not a forecasting claim.
- **Model:** the landmark logistic hazard on `ABCDx`, fitted on all rows from 2012 to 2026-11-20 with a ridge of C = 100 (D-026 clarification 2), plus
  - `post` (1 from 2025-10-07, the seed's `ftse_upgrade_announced` date), and
  - `post` × each of the H2 channels and their direction terms: `spx_ret`, `nasdaq_ret`, `vix_chg`, `ust10_chg`, `dxy_ret`, each with its `_xdir` term (10 terms).
- **Test:** a joint Wald test of the 10 `post` interactions, with standard errors clustered by date. A tiny ridge (C = 100) is used only so the fit converges.
- **Placebos:** the same statistic at 7 October of each year from 2013 to 2023, each with a 13-month post window and the sample ending before the real announcement. The paper reports where the real statistic ranks among the 11 placebos.
- **Claim:** H4 is supported only if the joint test has p < 0.05 **and** the real statistic exceeds every placebo. Otherwise the paper reports "not detected", with the power caveat. The effective date (2026-09-21) is too recent to test; it is reported descriptively only.

**5b. Decision at the HOSE close (proposal robustness).** Proposed meaning: the same features, all of which are public before 09:00 on t+1 and so before the close of t+1, and the same labels. Only the trading test executes at the **close of t+1** (14:45 ATC price) instead of the open. This checks that the result does not depend on open-auction prices. A version that adds same-day Asian closes would need new block-D timing in dbt and a new snapshot. It is not proposed.

**5c. Other proposal robustness checks** (main specification `ABCDx` against KM and `M`, plus the trading test, on the same folds):
- k = 1.5 and 3, with labels and features rebuilt from the same snapshot;
- sub-periods 2017–2019, 2020–2021, 2022, 2023–2026, cut from the pooled test rows (the proposal's 2012–2019 period starts in training, so its test part is 2017–2019);
- banks vs other VN30 stocks (test rows split by `is_bank`);
- excluding rows where t closed at the price limit;
- foreign flows added with a missing indicator (D-012).

**5d. Abolmakarem et al. appendix (proposal).** Run on development data only (2012–2016), random vs chronological split. It shows the leakage effect without touching the test years.

**5e. SHAP** (proposal; descriptive): computed for GBM and `nn_seq_ABCD` on the 2026 refit only, on a sample of 5,000 test rows. Explanation only; no test.

## 6. Guards and logging

- The runner refuses to start unless:
  - the working tree is clean;
  - the snapshot's derived inputs are present;
  - `--final --i-confirm-final-run` is given.
- It writes one run folder with the configuration, snapshot id, commit, every cached prediction (Parquet, git-ignored), `metrics.json` and a log. Every run, including a crash or a stop for leakage, is listed in `RUNS.md`.
- **Stops:** any pooled C above 0.70, or a shuffled control whose mean of per-year mean C lies outside 0.5 ± 0.03, halts the run before any further output is read. The trading test and RQ4 refuse to run without a passed evaluation (D-026 clarifications).
- **Before the run:** an end-to-end test on a synthetic dataset (known signal planted in fake "test years"), and a leakage review of the runner code (D-025).

## 7. Compute (decided: vast.ai)

- **Size:** training sets for the 10 years run from 40k to 130k rows, about 3.6 times the development folds on average. The development analyses took about 9 hours for 3 folds. Even with each specification tuned once per year and predictions reused, the final run is about 40–50 hours on the laptop. The random survival forest is the most uncertain part.
- **Options:**
  1. **Laptop, in tmux:** about 2–3 days. Years are independent, so 2–3 run in parallel within 16 GB.
  2. **vast.ai:** years in parallel, a few hours, with the agreed constraints: no `.env`, no Paper 2 data (the snapshot's `paper2/` folder is left out), and the machine specs recorded.
  3. **Laptop, with RSF limited to the D-014 grid's smaller leaf size** if it proves too slow. This is a reduction and would be logged.

**Decision (2026-11-26): vast.ai, one large instance (runbook §4b) running all years in parallel; the earlier one-year-per-instance plan below is the fallback.**

**Original plan: option 2, vast.ai.**
- **Runner:** works one test year at a time (`--year`), so years run on separate instances. The pooled evaluation runs on the laptop from the returned caches.
- **Copied to each instance:**
  - a `git bundle` of the run commit, so the commit is recorded and there is no `.env` and no untracked files;
  - the frozen snapshot without its `paper2/` folder.
- **Recorded per year:** instance type, CPU and RAM, Python and package versions (`uv.lock` hash) and wall time.
- **Returned:** the prediction caches and logs. The instance is destroyed afterwards.
