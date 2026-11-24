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

## Next steps

1. Reference prices and dated price limits (in progress); decide how disputed corporate actions are handled.
2. Compile VN30 membership history from HOSE announcements; verify the launch date.
3. Fill or document the gaps: pre-transfer HNX history (ACB, SHB) and index levels.
