# Research design decisions

Every clarification of, or change to, the pre-specified design (CLAUDE.md, "Research rules") is recorded here **before** it is used in a run. Each entry gives the date, the decision, the reason, and whether any data snapshot or model run existed at the time. Never edit a past entry; add a new one that supersedes it.

---

## D-001 — Exact study period

- **Date:** 2026-11-24
- **Type:** clarification (CLAUDE.md said only "2012–2026")
- **Decided by:** the author, on the author's instruction
- **State when decided:** no snapshot frozen, no swing labels computed, no model fitted. Raw CafeF archives up to 2026-11-23 were downloaded, but no prices were analysed against outcomes.

**Decision**

| Item | Value |
| --- | --- |
| First session in the sample | **2012-01-03** (first HOSE session of 2012; 2012-01-02 was the New Year holiday) |
| Last session in the sample | **2026-11-20**, up to that session's close (the last trading day of the week before this decision) |
| Training | Expanding window from 2012-01-03, refit each January (unchanged) |
| Test years | 2017–2026 (unchanged). **2026 is a partial test year: 2026-01-01 to 2026-11-20.** |
| Warm-up | Data from 2011-10-01 may be used **only** to initialise trailing quantities (ATR20, the directional-change state). No swing, label or row before 2012-01-03 enters the sample. |
| VN30 universe | A stock enters the VN30 universe only from the first effective date of the VN30 basket. VN30 launched in early 2012 (believed to be 2012-02-06; **to be verified** against HOSE's announcement and recorded in a later entry). Banks are in the universe from 2012-01-03 or their listing date, whichever is later. |

**End-of-sample rule**

- Outcomes are observed only up to the close of 2026-11-20. Data after that close, already in the raw layer, must not enter any feature, label or outcome.
- A swing still open at that close is right-censored at 2026-11-20.
- The fixed 5-trading-day horizon label for decision date d is censored when its window extends past 2026-11-20.
- The last decision time in the sample is 09:00 `Asia/Ho_Chi_Minh` on 2026-11-20, using information available before it.
- Global-market data for features is needed only up to that decision time.

**Reason**

- The author fixed the end date at the last completed trading week, rather than waiting for the end of 2026, so the work isn't blocked.
- The start date is the first session of the year CLAUDE.md specifies.
- Both are fixed before any outcome is examined, so neither was chosen to improve results.

**Consequences**

- The snapshot builder must filter to sessions 2012-01-03 through 2026-11-20 (warm-up rows flagged and excluded from the sample).
- The paper reports 2026 as a partial test year with its exact end date.
- A dbt or pytest check should fail if any sample row, label or outcome is dated after 2026-11-20.

---

## D-002 — Keep, and flag, prices whose open or close lies outside the day's high–low

- **Date:** 2026-11-24
- **Type:** data-cleaning rule (not a change to the modelling design)
- **Decided by:** the author, choosing between two options presented with evidence
- **State when decided:**
  - No snapshot frozen, no swing labels computed, no model fitted.
  - The decision was based only on data-quality counts (`qa_cafef_summary`), not on any outcome or result.

**Evidence**

- In the pinned CafeF raw archive (Upto 2026-11-23), 12,366 ordinary-share rows have open or close outside [low, high]; 6,148 of them fall in the study period (about 0.2% of stock-days).
- The excess is small: a median of 1.8% (open) and 2.4% (close).
- The rows cluster in specific years (2019, 2023–24).
- This pattern fits opening and closing auction prices (ATO/ATC) recorded outside the continuous-session high–low, rather than corrupted values.

**Decision**

- These rows stay in `prices_daily_raw` with the flag `ohlc_outside_range = true`; they are no longer quarantined.
- All other checks still reject: invalid ticker, conflicting duplicate, exchange conflict, non-positive price, high < low, negative volume, weekend.

**Reason**

- Rejecting the rows would leave gaps in the price series. Gaps distort the trailing ATR20 and the timing of swings for the affected stocks.
- The close price, on which swings are built, is most likely valid on these days.

**What does not change**

- ATR20 keeps its standard definition (true range from high, low and previous close). Any change to it would be a separate decision.
- The flag stays available, so a robustness check can drop flagged days and compare results.
