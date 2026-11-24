# Week-1 feasibility: research data sources

Started 2026-11-24. This tracks whether the data the paper needs can be obtained, from where, and under what terms. Order follows the decision to finish the research before the platform. Filing-PDF availability (the platform's Phase 3 risk) is deferred.

## What the paper needs

| Need | Detail |
| --- | --- |
| Daily OHLCV, 2012–2026 | VN30 members (including those later removed) and all listed banks, on HOSE, HNX and UPCoM |
| Raw (unadjusted) prices plus corporate actions | CLAUDE.md rule 7: store raw prices and compute adjustments ourselves |
| Exchange reference price per day | Price-limit checks use the reference price, not the previous close (rule 6) |
| VN30 membership by date | Semi-annual reviews since the index launched in Feb 2012 |
| Global market data | yfinance (`auto_adjust=False`), FRED, GPR index |

## Finding 1: vnstock is no longer freely installable (2026-11-24)

- `vnstock`, `vnstock3` and `vnai` return **404 on PyPI**: the packages were removed.
- The GitHub repo `thinh-vu/vnstock` is now a notice only. It says **versions before generation 6 stopped working on 10 November 2026**.
- Generation 6 (`vnstock==6.0.1`, `vnstock-oapi==0.1.2`) installs from vnstock's own index (`--extra-index-url https://vnstocks.com/api/packages`) under a proprietary licence. The connector (`vnstock-oapi`) is described as a free "Community" edition for personal, study and research use. Some libraries need a paid access package.
- Generation 6 **is not a data provider**. It connects to a source's official Open API using **API keys the user registers with that source** (e.g. a securities company), then normalises the result.

**Consequence:** the project's market-data source has to be chosen again. The paper needs a source with a clear licence and a reproducible history (2012 onward, raw prices, corporate actions). Options are listed below; the decision is the user's.

## Options for Vietnamese market data

| Option | For | Against / to verify |
| --- | --- | --- |
| A. vnstock gen 6 + a broker's Open API keys | Normalised schema across sources; matches the original plan | Proprietary package from a private index; its licence terms for published research need reading; history depth depends on the broker API |
| B. A broker's official Open API directly, through our own client | No third-party wrapper; we wrap libraries anyway (rule 7); clearer licence | Need an account and keys; must verify history depth back to 2012, raw vs adjusted, and delisted tickers |
| C. University-licensed data (LSEG Datastream/Workspace, Bloomberg, FiinPro) | Most credible for reviewers; usually has delisted stocks, corporate actions and index constituents | Depends on library access; licence may limit redistribution of snapshots |

## Finding 2: broker APIs ruled out; CafeF chosen (2026-11-24)

- The user found broker API registration impractical, and no university database is available, so options B and C are out and A is on hold.
- **CafeF's free bulk archives** meet the main needs: raw and adjusted files, all three exchanges from 2000, and delisted stocks included.
- **Yahoo Finance** lacks delisted stocks, so it can serve only as a cross-check.
- Full test results, known gaps and terms: [ADR 0002](adr/0002-market-data-source-cafef.md).
- **First ingestion (2026-11-24):** both archives up to 2026-11-23 are stored in the raw layer. The raw archive has 3,383,146 rows and 4,137 tickers (HSX 2,762, HNX 380, UPCoM 1,125; a ticker that changed exchange counts once per exchange).

## VN30 membership

Not yet investigated. No free source with history was found. Plan: compile it from HOSE's semi-annual review announcements, with source URLs, announcement dates and effective dates.

## Finding 3: CafeF archive stability and quality checks (2026-11-24)

**Raw history is not revised.** Comparing the 2026-11-20 and 2026-11-23 archives:
- Raw: 0 of 3,380,055 shared rows changed.
- Adjusted: rewrote 7,311 rows for 3 tickers (new corporate actions re-adjust history). We use raw and compute adjustments ourselves.

Daily downloads are therefore **not needed for the research**. They are deferred to the platform phase.

**Pinned archives.** `dbt/dbt_project.yml` pins both archives up to 2026-11-23. They are loaded into ClickHouse `raw_cafef_eod` (`ingestion/market/cafef_load.py`), then checked by dbt (`int_cafef__eod_checked`). Raw variant, ordinary shares:

| Outcome | Rows | Tickers | Notes |
| --- | ---: | ---: | --- |
| kept (`prices_daily_raw`) | 3,133,638 | 1,874 | 2,722,361 rows in the study period (D-001) |
| of which flagged `ohlc_outside_range` | 12,366 | 1,307 | kept with a flag (D-002); 6,148 in the study period |
| exact duplicate copy | 76 | 19 | merged into the kept row |
| `nonpositive_price` | 489 | 415 | mostly a missing "high" (0), e.g. 2025-05-05 on HNX/UPCoM |
| `weekend` | 247 | 246 | 245 on Sat 2023-08-26, most likely the KRX system test, not a trading day |
| `high_below_low` | 73 | 73 | |
| `exchange_conflict` | 4 | 2 | same ticker and date on two exchanges |

Other rows: 1,656 rows with a blank or "0" ticker (rejected), plus warrants (225k), funds/ETFs (21k) and 3 index-like tickers, all out of scope.

**`ohlc_outside_range`: kept with a flag** (`research/paper1/DECISIONS.md` D-002).
- The open or close is outside high–low by a median of 1.8–2.4%, clustered in 2019 and 2023–24.
- This looks like auction prices (ATO/ATC) recorded outside continuous-session high/low, not corruption.
- Rejecting the rows would leave gaps that distort ATR20 and swing timing, so they stay in `prices_daily_raw` with `ohlc_outside_range = true`.
- In the adjusted file, 98.7% of these cases are within 0.5% (rounding).

## Finding 4: corporate actions and adjusted prices (2026-11-24)

**Event detection** (`int_corporate_actions`).
- Events are found as jumps in CafeF's adjusted/raw ratio, with a tolerance set by CafeF's rounding (adjusted prices to 0.1 VND).
- **16,318 events across 1,556 stocks; 13,879 in the study period.**
- The ratio = previous raw close / theoretical reference price. It covers cash dividends, stock dividends, bonus shares, splits and rights.
- Two UPCoM events that follow long trading gaps (PTG after 695 days, VNX after 181 days) are flagged `after_long_gap` and treated as uncertain.

**Our adjusted prices** (`prices_daily_adjusted`) are raw prices divided by the ratios of all later events (CLAUDE.md rule 7).
- They reproduce CafeF's adjusted file up to one constant per stock. Only 17 of 2.72M study-period rows (one stock, VNX) differ by more than 0.5%, and the 99.99th-percentile difference is 0.04%.
- The constant arises because, for 65 stocks, CafeF applies an event dated after the stock's last trade to the whole series. That changes no return.

**Independent check against Yahoo Finance** (`qa_corporate_actions_vs_yahoo`).
- Sample: 45 HOSE banks and large caps with Yahoo coverage, study period only.
- Yahoo lacks the HNX/UPCoM banks and delisted stocks.

| Status | Events | Meaning |
| --- | ---: | --- |
| match | 565 (87%) | same ex-date, ratio within 1% |
| date_shift | 5 | same ratio, our date 1 day later (MWG, PNJ) |
| ratio_mismatch | 33 | same date, different ratio (e.g. VIB 2020-11-19: Yahoo 1.44, ours 1.20) |
| yahoo_only | 21 | mostly cash dividends with no CafeF adjustment (e.g. CII 2021-04-22, 1,400 VND, about 6.6%) |
| ours_only | 25 | events Yahoo lacks (e.g. VIC 2012-06-04, 1.275) |

Neither source is complete. An event missing from our series shows up as an artificial price jump on its ex-date. That matters for swing labelling, so disputed events need a rule before labelling (open decision).

## Finding 5: reference prices and dated price limits (2026-11-24)

**Dated schedules.** Researched from exchange rules and decisions, each row sourced, in `dbt/seeds/` (`research/paper1/DECISIONS.md` D-003).
- **Limits changed inside the sample:** HOSE ±5% to ±7% and HNX ±7% to ±10% on 2013-01-15; UPCoM ±10% to ±15% on 2015-07-01.
- **HOSE ticks changed on 2016-09-12.**
- **Reference price:** HOSE always used the previous close. HNX only from 2013-07-29; before that it used a VWAP. UPCoM always uses the previous session's VWAP, which CafeF does not publish.

**`prices_daily_limits`** gives, per stock-day: reference price, ceiling, floor, `close_at_ceiling`, `close_at_floor`, `outside_band`, regime and rule confidence.
- **Self-check:** on normal, non-event days, 0.09% (HOSE) and 0.07% (HNX) of stock-days trade outside the computed band. For HOSE it is 0.006–0.17% in most years and 0.6% in 2012, when the tick rule is partly unverified.
- **Event days:** 2–4% fall outside the band, because the exchange does not adjust the reference for some event types.
- **Coverage, study period:** HOSE 99.98% of stock-days computed; banks 85.7%. Not computed: the UPCoM banks KLB, SGB, ABB, PGB and VAB, plus NVB before 2013-07-29.

**Open questions from the research** (details in D-003 and the seeds' confidence column):
- the HOSE rules before 2012-03-05;
- case-by-case limits for HOSE resumptions before 2016 and for exchange transfers;
- whether the rounding rule applied before 2021.

## Finding 6: VN30 membership, bank list and coverage (2026-11-24)

**VN30.**
- Rebuilt from HOSE review results and ad-hoc replacements: 152 changes, 77 stocks, 2012-02-06 to 2026-08-03 (`research/paper1/DECISIONS.md` D-004).
- 30 members on every session; all 32 printed baskets match.
- Price coverage: 99.1% of member-days. Missing: HVG and PVF.

**Banks.**
- 29 banks with exchange spells, including HBB (merged 2012) and PCB (UPCoM 2026).
- CafeF's bulk archive keeps only a stock's history on its current exchange. Missing (`qa_bank_coverage`):

| Bank | Missing spell | Bank-days |
| --- | --- | ---: |
| ACB | HNX 2012 to 2020-12 | 2,224 |
| SHB | HNX 2012 to 2021-10 | 2,433 |
| VBB | UPCoM 2019 to 2026-06 | 1,721 |
| BVB | UPCoM 2020 to 2026-07 | 1,491 |
| VIB | UPCoM 2017 to 2020-10 | 951 |
| NAB | UPCoM 2020 to 2024-02 | 840 |
| BAB | UPCoM 2017 to 2021-02 | 785 |
| LPB | UPCoM 2017 to 2020-10 (28 days left, mislabelled HSX) | 763 |
| HBB | HNX 2012 to 2012-08 | 155 |

**CafeF per-ticker history** (`cafef.vn/du-lieu/Ajax/PageNew/DataHistory/PriceHistory.ashx`, US date format, 30 rows per page) has ACB, SHB and VIB for these periods; BVB and HBB are not there. It also returns matched trade value, which could give the VWAP that UPCoM and early HNX reference prices need.

**Universe** (`research_universe_daily`): 146,555 stock-days and 91 stocks; 91% have prices.

## Finding 7: gaps filled from CafeF per-ticker history (2026-11-24)

**Results** (`research/paper1/DECISIONS.md` D-006):
- **Agreement:** the per-ticker history matches the bulk archive on 100% of 8,251 overlapping stock-days (OHLC and volume).
- **Fills:** 13,055 rows fill the documented gaps.
- **Coverage, study period:** banks 99.0% of bank-days (was 83%); VN30 99.93% of member-days (was 99.1%). Only Habubank (HBB, 2012) is missing.
- **VWAP references:** UPCoM and early-HNX reference prices are rebuilt from VWAP where the rounded value pins them to one tick. That covers 5,395 bank-days, with 0.20% outside the band.
- **Banks with computed limits:** 85.2% of bank-days.
- **How to fetch:** `src/vnbank/ingestion/market/cafef_history_ingest.py` (FETCH_PLAN), resumable. Raw zips are under `cafef_history/` in the raw layer.

## Finding 8: disputed corporate actions adjudicated (2026-11-24)

**How it was done** (`research/paper1/DECISIONS.md` D-007, D-008):
- **Event detection** now also covers the gap-filled periods (e.g. ACB's 7 events during its HNX years).
- **The Yahoo cross-check** covers all 91 universe stocks.
- **Queue:** 83 disputed events plus 5 that failed the price-limit check.
- **Checking:** research agents established the facts from official notices (56 from exchange/depository notices, 32 secondary). The ratio is computed by one tested formula (`corporate_action_ratio` macro).
- **Spot checks:** 3 of 3 passed against the original HOSE PDFs.

**Who was right** on the 88 events:
- CafeF-based inference right, Yahoo wrong: 64.
- Yahoo right, ours wrong: 17.
- Both wrong: 7.

**What each source gets wrong:**
- **Yahoo:** omits rights issues entirely; sometimes compounds stock dividend and bonus (HDB 2020: 1.3225 vs 1.30) or applies a split twice (VIB 2020: 1.44 vs 1.20); lists non-existent dividends (VIB 2022, MBB 2019); some dates are one day early (2018–19).
- **CafeF:** some wrong adjustments (TPB 2018, MWG 2025: an 11% phantom move); missing dividends (TPB 2025, GMD 2018, HSG 2018); and phantom events on exchange-transfer days (KLB, VAB).

**Result:**
- `int_corporate_actions_final`: 82 adjudicated and 558 inferred events on universe stock-days.
- Agreement with Yahoo: 85.7% → 88.6%. The remainder is mostly known Yahoo errors.

## Finding 9: global series for feature block D (2026-11-24)

**Series and coverage.**
- Series follow `docs/proposals/paper1-trend-reversals.md`, with the source changes in D-009: Brent `BZ=F`, USD/CNY `CNY=X`, and DGS10 timed by the Treasury's 18:00 ET publication.
- Everything is loaded from 2000 onward (Brent from 2007, USD/VND from 2003). Yahoo has no CSI 300 history, so the Shanghai Composite (`000001.SS`) replaces it (D-010).

**Timing.**
- `available_at_utc` per series comes from seed `global_series` (close time in the market's own time zone, so daylight saving is handled).
- GPR is updated on Mondays and treated as public from the Wednesday after (median staleness 11 days).
- The GPR file's hindsight `event` labels are never loaded.

**Tables and checks.**
- `global_asof_daily` and `global_features_daily` pass `no_feature_after_decision_time`, the CLAUDE.md rule-4 test, now implemented.
- Check case: the first session after Tết 2024 carries the S&P 500's cumulative move since the last pre-Tết decision (+0.93%).

## Finding 10: block C, snapshot dev-v1 and the first labels (2026-11-24)

**Block C** (`local_market_daily`).
- Previous session's VN-Index and VN30 close and return, HOSE breadth on adjusted returns, matched value and foreign net buying.
- Look-ahead test and a NaN/Inf guard pass.
- **Foreign flows are missing on 570 sessions, mostly 2019-04 to 2021-07** (CafeF has 59, 22 and 128 days for 2019, 2020 and 2021). Decision pending.

**Snapshot dev-v1** `b536ec69488162e0` (`research/snapshots.md`): universe, raw and adjusted prices from the 2011-10-01 warm-up, limits, corporate actions, sessions, membership and features.

**First labels** (`research/paper1/runs/RUNS.md`; descriptive only, no model):

| k | Survival rows | Reversals (study) | Median swing age at reversal | Rows reversing within 5 days |
| --- | ---: | ---: | ---: | ---: |
| 2 (main) | 139,241 | 13,980 | 26 | 26.3% |
| 1.5 | 139,241 | 20,288 | 20 | 36.2% |
| 3 | 139,241 | 7,862 | 42.5 | 15.3% |

Stocks with no rows: HBB (no data), MCH and PCB (fewer than 250 days of history).

## Finding 11: first development evaluation, inside 2012–2016 only (2026-11-24)

**Setup.**
- Features (blocks A–D) are assembled from snapshot dev-v1; the look-ahead rule is re-checked in Python.
- Runner: purged, embargoed inner cross-validation with folds 2014, 2015 and 2016 (expanding training from 2012). Validation labels are censored at 2016-12-31. **No test year (2017–2026) was evaluated** (D-012).

**Two problems found and fixed before trusting any result.**
- The hazard was badly calibrated: chaining one-day hazards with features held fixed exaggerated risk in both directions. It is now fitted by landmarking (D-013).
- A single shuffled-label draw is noisy, because rows of one swing are correlated. The control now uses 10 seeds and checks the mean.

**Current development results** (logistic hazard on blocks A–D; `research/paper1/runs/RUNS.md`):

| Fold | Uno C (KM) | Uno C (hazard) | Shuffled C (mean of 10) | IBS KM / hazard | td-AUC 5 / 10 / 20 days |
| --- | ---: | ---: | ---: | --- | --- |
| 2014 | 0.500 | 0.595 | 0.505 | 0.209 / 0.201 | 0.670 / 0.607 / 0.588 |
| 2015 | 0.500 | 0.591 | 0.497 | 0.210 / 0.204 | 0.668 / 0.614 / 0.569 |
| 2016 | 0.500 | 0.608 | 0.500 | 0.204 / 0.194 | 0.689 / 0.625 / 0.599 |

A modest, stable signal, well below the "too good" alarm (C > 0.70). Calibration at 5 days is slightly too narrow (predicted 0.17–0.44 against 0.11–0.56 observed).

## Finding 12: model comparison and the global-block ablation, development only (2026-11-24)

**Setup** (D-014; run `20261124T083349Z-devcompare`).
- Same folds as Finding 11 (2014, 2015, 2016 inside 2012–2016).
- Each model is tuned on the last training year by integrated Brier score (IBS), then refitted.
- Intervals: paired moving-block bootstrap (blocks of 20 sessions, 200 resamples), pooled over the three folds.
- **No test year was evaluated.**

| Model (blocks A–D unless noted) | Uno C, pooled [95% CI] | IBS, pooled | IBS minus KM [95% CI] | td-AUC 5 / 10 / 20 days |
| --- | --- | ---: | --- | --- |
| Kaplan–Meier | 0.501 | 0.2076 | — | 0.499 / 0.503 / 0.504 |
| Logistic hazard (C = 0.01, l1 0.5) | 0.600 [0.588, 0.610] | 0.1991 | [−0.0101, −0.0064] | 0.680 / 0.619 / 0.587 |
| Cox (ridge α = 100) | 0.598 [0.586, 0.608] | 0.1995 | [−0.0101, −0.0058] | 0.676 / 0.615 / 0.585 |
| Random survival forest | 0.586 [0.572, 0.599] | 0.1980 | [−0.0111, −0.0078] | 0.679 / 0.614 / 0.576 |
| Gradient-boosted hazard | 0.577 [0.563, 0.590] | 0.2000 | [−0.0104, −0.0043] | 0.670 / 0.608 / 0.567 |
| Logistic hazard, blocks A–C | 0.604 [0.593, 0.613] | 0.1984 | [−0.0106, −0.0073] | 0.686 / 0.623 / 0.591 |

Shuffled-label control (mean of 10 seeds): 0.502 / 0.496 / 0.498. No warnings.

**Reading.**
- **RQ1:** every model beats KM on IBS, and every interval excludes zero (one exception: GBM in 2014, upper bound +0.0002). The signal is modest and stable across folds.
- **Model choice:** the penalised linear models (logistic hazard, Cox) rank best. The forest is level on IBS and boosting is weakest. With a weak signal this favours the interpretable main model in the proposal.
- **RQ2 (global block D), development years:** adding D does not help.
  - Pooled A–D minus A–C: C [−0.008, 0.001], IBS [−0.0000, 0.0014].
  - In 2016 alone D is slightly *harmful*: C [−0.009, −0.001], IBS [+0.0002, +0.0023].
  - This is 2014–2016, before the market upgrade. H4 predicts global effects grow later, so the question is settled only by the final run on 2017–2026. A null result there is still reported.
- **Short horizons are more predictable:** td-AUC is about 0.68 at 5 days against about 0.59 at 20. This is below the alarm level, but its source (swing age vs. features) should be decomposed before writing it up.
- **Caveat on pooled metrics:** the pooled metrics use the last fold's training data for the censoring weights. Per-fold numbers are the primary ones.

## Finding 13: where the short-horizon signal comes from, development only (2026-11-24)

**Setup** (D-015; run `20261124T100544Z-devdecompose`).
- The tuned logistic hazard is fitted on nested feature sets. Intervals use the D-014 bootstrap.
- **No test year was evaluated.**

| Feature set | Uno C, pooled | 5-day td-AUC [95% CI] | IBS |
| --- | ---: | --- | ---: |
| Kaplan–Meier | 0.501 | 0.499 | 0.2076 |
| Swing age only | 0.529 | 0.540 [0.514, 0.565] | 0.2070 |
| Block A (swing state) | 0.600 | 0.679 [0.661, 0.692] | 0.1989 |
| A + B (stock technicals) | 0.604 | 0.685 [0.667, 0.697] | 0.1983 |
| A + B + C (local market) | 0.604 | 0.686 [0.670, 0.699] | 0.1984 |

Paired differences in 5-day td-AUC, pooled:
- A − age: [+0.115, +0.162];
- AB − A: [+0.002, +0.009];
- ABC − AB: [−0.004, +0.007].

**Reading.**
- **Not mainly a swing-age effect.** Age reaches 22% of the skill above chance at 5 days, below the 80% rule fixed in D-015.
- **But one feature carries almost all of it.** Used alone with no fitting (D-015 addendum), `swing_dist` reaches a 5-day td-AUC of 0.671; the full model reaches 0.686. `swing_dist` measures how far the price has already moved back from the swing's extreme, where −1 is the confirmation trigger. The other block-A features score 0.50–0.55 alone.
- **Interpretation.** Much of the measured predictability is partly mechanical: a swing that has already retraced most of its threshold needs only a small further move to be confirmed as a reversal. It is a legitimate forecast (known at the 09:00 decision time) but not evidence of behavioural predictability. Stock technicals add a small, real amount; the local market adds nothing detectable in 2014–2016.
- **Consequence for the paper (proposal, needs a decision).** Incremental claims (RQ2–RQ4) should be measured against a *mechanical baseline* (swing age + `swing_dist`), not only against Kaplan–Meier.

## Finding 14: against the mechanical baseline, development only (2026-11-24)

**Setup** (D-016, approved; run `20261124T114352Z-devdecompose-D-016`).
- The mechanical baseline M is the logistic hazard on swing age + `swing_dist`.
- All sets are tuned as in D-014; pooled bootstrap intervals.
- **No test year was evaluated.**

| Feature set | Uno C, pooled | IBS | 5-day td-AUC |
| --- | ---: | ---: | ---: |
| Kaplan–Meier | 0.501 | 0.2076 | 0.499 |
| M (mechanical) | 0.593 | 0.1995 | 0.671 |
| M + B (stock technicals) | 0.601 | 0.1986 | 0.683 |
| M + B + C (local market) | 0.601 | 0.1987 | 0.683 |
| M + D (global, additive) | 0.592 | 0.2003 | 0.668 |
| A–C | 0.604 | 0.1984 | 0.686 |
| A–D | 0.600 | 0.1991 | 0.680 |

Paired differences, pooled [95% CI]:

| Comparison | Uno C | IBS |
| --- | --- | --- |
| A–C − M | [+0.0004, +0.0198] | [−0.0024, +0.0004] |
| M+B − M | [+0.0009, +0.0145] | [−0.0018, +0.0001] |
| M+B+C − M+B | [−0.0031, +0.0037] | [−0.0004, +0.0006] |
| M+D − M | [−0.0086, +0.0056] | [−0.0001, +0.0018] |
| A–D − A–C | [−0.0079, +0.0011] | [−0.0000, +0.0014] |

**Reading.**
- **Predictability beyond the label mechanics is not established in development.** The full local model ranks slightly better than M (C interval excludes zero), but its probability accuracy (IBS) is not better. D-016 requires both, so the verdict is **no**. Per fold, only 2016 passes both.
- What survives beyond the mechanics is a small ranking gain, mostly from stock technicals (block B).
- The local market (C) adds nothing over B.
- **Global features in additive form add nothing and slightly hurt** (2016: M+D − M, C [−0.014, −0.000]). D-017 tests whether this is the direction-cancellation problem.
- **Implication for the paper.** If this holds in the final run, the main RQ1 statement becomes "reversal timing is largely determined by the swing's position relative to the threshold; feature-based predictability beyond that is small." That is reported as found.

## Finding 15: direction-specific effects; the global block still adds nothing, development only (2026-11-24)

**Setup** (D-017, pre-registered; run `20261124T133305Z-devdecompose-D-017`).
- Every feature in blocks B–D also enters as `swing_dir` × feature, so, for example, a US fall can raise the hazard of an up-swing ending and lower it for a down-swing.
- Logistic hazard tuned as in D-014; pooled bootstrap intervals.
- **No test year was evaluated.**

| Feature set | Uno C, pooled | IBS |
| --- | ---: | ---: |
| M (mechanical) | 0.593 | 0.1995 |
| M + B + C, additive | 0.601 | 0.1987 |
| M + B + C, direction-specific | 0.606 | 0.1978 |
| M + B + C + D, direction-specific | 0.599 | 0.1994 |
| A–C, direction-specific | 0.604 | 0.1982 |
| A–D, direction-specific | 0.596 | 0.1998 |

Paired differences, pooled [95% CI]:

| Comparison | Uno C | IBS |
| --- | --- | --- |
| Direction-specific − additive (M+B+C) | [−0.004, +0.013] | [−0.0024, +0.0009] |
| **A–D − A–C, direction-specific (RQ2)** | [−0.015, +0.001] | [−0.0001, +0.0033] |
| M+B+C+D − M+B+C, direction-specific | [−0.016, +0.001] | [−0.0002, +0.0032] |
| A–C (direction-specific) − M | [−0.001, +0.023] | [−0.0033, +0.0007] |

**Reading.**
- **The global null is not an artefact of the additive specification.** Even when global shocks can act in opposite directions on up- and down-swings (the form H2 states), adding them does not help. In 2014 and 2016 they make the model worse (2016 A–D − A–C: C [−0.014, −0.001], IBS [+0.0004, +0.0037]). The 14 global series and their interactions add 28 noisy columns that the model partly fits as noise.
- **Direction-specific slopes help the local blocks a little,** significantly in 2016 only, not pooled.
- **Beyond the mechanics** the verdict is unchanged from Finding 14: a small ranking gain at most, not significant on both metrics.
- **Per the D-017 guard, no further block-D specifications will be tried on development data,** except the pre-specified bank × global interactions of RQ2. RQ2 and RQ4 are decided by the final run on 2017–2026. H4 (global effects grow after market upgrading) remains open, since 2014–2016 is pre-upgrade.

## Finding 16: gold and each global feature, development only (2026-11-24)

**Setup** (D-018 and its pre-run amendment; run `20261124T151155Z-devattribution-D-018`).
- Each of the 14 global features is dropped in turn (the feature and its direction interaction) from the D-017 model `ABCDx`, using the hyperparameters chosen there.
- Change in IBS over the pooled dev folds: 2,000 paired block-bootstrap resamples, Holm-adjusted across the 14 features.
- **No test year was evaluated.**

| Feature | ΔIBS when dropped (> 0 = feature helps) | 95% CI | p (raw) | ΔC (point) |
| --- | ---: | --- | ---: | ---: |
| gold_ret | +0.00007 | [−0.00001, +0.00019] | 0.12 | +0.0003 |
| usdcny_ret | +0.00003 | [−0.00005, +0.00012] | 0.41 | +0.0002 |
| vix_chg | +0.00000 | [−0.00009, +0.00010] | 0.91 | +0.0000 |
| spx_ret | −0.00003 | [−0.00008, +0.00004] | 0.43 | −0.0002 |
| sse_ret | −0.00012 | [−0.00031, +0.00006] | 0.26 | −0.0005 |
| vix_level | −0.00069 | [−0.00165, +0.00012] | 0.09 | −0.0030 |
| gpr_level | −0.00091 | [−0.00241, +0.00026] | 0.16 | −0.0040 |
| (the other 7) | between −0.00005 and 0.00000 | all include 0 | ≥ 0.25 | |

All Holm-adjusted p-values are 1.0, so **no global feature is informative** in 2014–2016.

**Gold vs geopolitical risk.**
- Gold given GPR: ΔIBS +0.00007 [−0.00001, +0.00019], ΔC +0.0003 [−0.0000, +0.0009].
- GPR given no gold: ΔIBS −0.0009 [−0.0024, +0.0002].
- Gold is the only global series whose point estimates favour it on both metrics, but the effect is tiny and not significant. GPR adds nothing even without gold.

**Reading.**
- **Gold is noise for reversal timing in these years.** It is not a significant channel, with or without the geopolitical index.
- **The slight harm from block D comes mainly from the two *level* series,** VIX level and GPR level. Levels drift over time, so a slope fitted on earlier years extrapolates poorly.
- Per the D-017 guard this is recorded and **not acted on** with development data: no re-specification of the levels. In the final run the levels stay as pre-specified. A standardised-level variant may be reported only as a robustness check labelled as motivated by development results.
- **Limitation (from the Paper 2 data scout):** GPR history is revised, and the snapshot uses the current vintage. Vintages exist only from 2022-02-24, so first-release values cannot be rebuilt for 2012–2021.

## Next steps

1. Done (Finding 12). Next on the modelling side: neural hazard model; decompose the 5-day td-AUC (swing age vs. features); block E (bank fundamentals, news).
2. Before the trading test: decide how stock-days without computable limits are treated.
3. Index levels (VN-Index, VN30) still needed.
