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

## Next steps

1. Schedule daily CafeF downloads to build a dated vintage of each file.
2. Stage CafeF data in ClickHouse with quality checks: duplicates, non-positive prices, high < low, warrant/ETF filtering.
3. Infer corporate actions from the adjusted/raw ratio, then compute our own adjustments and reference prices.
4. Compile VN30 membership history from HOSE announcements.
5. Fill or document the gaps: pre-transfer HNX history (ACB, SHB) and index levels.
