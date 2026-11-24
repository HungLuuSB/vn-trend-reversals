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

**`ohlc_outside_range`: kept with a flag** (`research/DECISIONS.md` D-002).
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

**Dated schedules.** Researched from exchange rules and decisions, each row sourced, in `dbt/seeds/` (`research/DECISIONS.md` D-003).
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
- Rebuilt from HOSE review results and ad-hoc replacements: 152 changes, 77 stocks, 2012-02-06 to 2026-08-03 (`research/DECISIONS.md` D-004).
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

**Results** (`research/DECISIONS.md` D-006):
- **Agreement:** the per-ticker history matches the bulk archive on 100% of 8,251 overlapping stock-days (OHLC and volume).
- **Fills:** 13,055 rows fill the documented gaps.
- **Coverage, study period:** banks 99.0% of bank-days (was 83%); VN30 99.93% of member-days (was 99.1%). Only Habubank (HBB, 2012) is missing.
- **VWAP references:** UPCoM and early-HNX reference prices are rebuilt from VWAP where the rounded value pins them to one tick. That covers 5,395 bank-days, with 0.20% outside the band.
- **Banks with computed limits:** 85.2% of bank-days.
- **How to fetch:** `ingestion/market/cafef_history_ingest.py` (FETCH_PLAN), resumable. Raw zips are under `cafef_history/` in the raw layer.

## Finding 8: disputed corporate actions adjudicated (2026-11-24)

**How it was done** (`research/DECISIONS.md` D-007, D-008):
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
- Series follow `docs/proposal.md`, with the source changes in D-009: Brent `BZ=F`, USD/CNY `CNY=X`, and DGS10 timed by the Treasury's 18:00 ET publication.
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

**First labels** (`research/runs/RUNS.md`; descriptive only, no model):

| k | Survival rows | Reversals (study) | Median swing age at reversal | Rows reversing within 5 days |
| --- | ---: | ---: | ---: | ---: |
| 2 (main) | 139,241 | 13,980 | 26 | 26.3% |
| 1.5 | 139,241 | 20,288 | 20 | 36.2% |
| 3 | 139,241 | 7,862 | 42.5 | 15.3% |

Stocks with no rows: HBB (no data), MCH and PCB (fewer than 250 days of history).

## Next steps

1. Feature blocks A (swing state) and B (stock technicals) from the snapshot; Kaplan-Meier baseline and shuffled-label control; walk-forward runner.
2. Before the trading test: decide how stock-days without computable limits are treated.
3. Index levels (VN-Index, VN30) still needed.
