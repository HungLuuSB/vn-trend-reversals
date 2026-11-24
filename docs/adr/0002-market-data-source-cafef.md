# ADR 0002: CafeF bulk archives as the primary source of Vietnamese daily prices

- **Status:** accepted
- **Date:** 2026-11-24

## Context

The paper needs daily OHLCV for VN30 members and all listed banks, 2012–2026. That means raw (unadjusted) prices, so we can compute adjustments ourselves (CLAUDE.md rule 7), and stocks that were later delisted, so the sample has no survivorship bias.

vnstock left PyPI. Generation 6 only connects to a broker's Open API using the user's own keys, and the user found broker API registration impractical. No university database (Datastream, WRDS, FiinPro) is available.

## Options tested on 2026-11-24

| Option | Result |
| --- | --- |
| CafeF bulk archives | Free, no registration. Separate raw and adjusted files. HOSE, HNX and UPCoM from 2000. Includes delisted stocks (FLC to 2022, ROS to 2022, ITA to 2024). |
| Yahoo Finance (`.VN`) | No delisted stocks (FLC and ROS missing), same exchange-transfer gaps, about 4 days behind. |
| vnstock gen 6 + broker API | Needs broker accounts and API keys. |

**Checks on the raw file:**
- Raw and adjusted prices differ on 72% of rows.
- On HOSE ordinary shares from 2013, 1,521 day-to-day moves exceed 7.5%. Of these, 1,364 fall exactly on dates where the adjusted/raw ratio changes (corporate actions). The other 157 are mainly tick-size rounding at low prices, new listings and resumptions. This is how genuinely raw data behaves.

## Decision

- **Main price source:** CafeF's raw archive (`CafeF.SolieuGD.Raw.UptoDDMMYYYY.zip`).
- **Adjusted archive:** downloaded too, used only for cross-checks and to infer corporate-action dates and ratios.
- **Storage:** both are stored unchanged in the raw layer by `ingestion/market/cafef_ingest.py`. Downloading every trading day keeps a dated vintage of each file.
- **Yahoo Finance:** an independent cross-check for HOSE prices.
- **vnstock gen 6:** stays installed, unused, as a fallback.

## Known gaps and how they will be handled

1. **History before an exchange transfer is missing for older transfers** (ACB on HNX 2006–2020, SHB on HNX to 2021). Affects the bank sample only; VN30 is HOSE. To be filled from another source or documented as a sample limitation.
2. **No index levels** (VN-Index, VN30). Separate source needed.
3. **No explicit corporate actions or exchange reference prices.** Infer ex-dates and ratios from the adjusted/raw ratio and validate them against published events. The reference price follows from the previous close and the corporate action.
4. **Data quality:** 1,726 duplicate ticker-date rows (7% with conflicting prices), some non-positive prices (mostly 2025) and rows with high < low. Quality checks will quarantine these, not drop them silently.
5. **Rows that aren't ordinary shares:** covered warrants, ETFs and index-like tickers are mixed in. Filter them by ticker pattern and listing type.

## Terms and citation

CafeF (© VCCorp) publishes no terms of use for these downloads; the page says the data is for reference. We use it for research only, cite it as "CafeF (VCCorp), end-of-day data archive, downloaded <date>", and never redistribute the files. Data stays out of git (rule 2).
