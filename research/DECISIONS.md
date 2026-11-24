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

---

## D-003 — Price limits follow the rules in force on each date; reference prices only where reconstructable

- **Date:** 2026-11-24
- **Type:** clarification of CLAUDE.md data rule 6, which listed only today's limits (±7% / ±10% / ±15%)
- **Decided by:** approved by the author as part of the step-2 plan; details set from sourced research
- **State when decided:** no snapshot, no swing labels, no model. Decided before any limit-hit statistic was used for anything but data-quality checks.

**Decision**

Limits, tick sizes and the reference-price rule are dated schedules in `dbt/seeds/`, one row per rule, each with its legal basis, source URL and confidence (`verified-official`, `verified-secondary`, `unverified`).

| Exchange | Normal limit | Reference price |
| --- | --- | --- |
| HOSE | ±5% to 2013-01-14; ±7% from 2013-01-15 | previous close (always) |
| HNX | ±7% to 2013-01-14; ±10% from 2013-01-15 | session VWAP to 2012-03-25; last-15-minute VWAP to 2013-07-28; previous close from 2013-07-29 |
| UPCoM | ±10% to 2015-06-30; ±15% from 2015-07-01 | previous session's VWAP (always) |

Tick sizes:
- **HOSE:** 100 / 500 / 1,000 VND before 2016-09-12; 10 / 50 / 100 VND from 2016-09-12.
- **HNX and UPCoM:** 100 VND.

How the bands are computed:
- The ceiling is rounded down and the floor rounded up, to the tick of their own price level. This rounding is explicit in the rules from 2021 and assumed for earlier years.
- On ex-dates, the reference = previous close / corporate-action ratio.

**Where limits are not computed** (`limit_status != 'computed'`):
- **The reference was a VWAP** (UPCoM always; HNX before 2013-07-29). CafeF does not publish traded value, so it cannot be reconstructed. Status: `ref_not_reconstructable`.
- **Special regimes:** new listings, exchange transfers (decided case by case: ACB got ±20%, SHB ±7%), and HOSE resumptions before 2016-09-12 (also case by case).

**Evidence that the schedule is right**
- On normal, non-event days, only 0.09% of HOSE and 0.07% of HNX stock-days trade outside the computed band (study period).
- The remaining cases are mostly data errors or missed corporate actions; the `outside_band` flag keeps them visible.

**Consequences for the research**
- HOSE (all VN30 members) has computed limits on 99.98% of stock-days.
- Banks: 85.7% of stock-days. Not covered: the UPCoM banks (KLB 2017–2026, SGB, ABB, PGB, VAB) and NVB before 2013-07-29.
- For those stock-days, the trading test's "no fill at limit-down" rule cannot be applied exactly. How to treat them must be decided before the trading test is run.

---

## D-004 — VN30 membership and the bank list (point-in-time universe)

- **Date:** 2026-11-24
- **Type:** clarification (completes D-001, which left the VN30 launch date to be verified)
- **State when decided:** no snapshot, no swing labels, no model.

**Decision**

- **VN30 launch:** 2012-02-06, with the 30-stock basket announced by HOSE on 2012-01-30. Confirmed by two independent texts (hanoimoi.vn 2012-02-02; baochinhphu.vn 2012-02-07). No HOSE original was found, so confidence is verified-secondary.
- **Membership is point in time** (`dim_vn30_membership`, seed `vn30_changes`).
  - A stock is a member from the effective date of its addition (the first trading day the new basket applies) to the day before the effective date of its removal.
  - Announcement dates are kept for look-ahead audits.
  - The history has 152 changes and 77 stocks: 28 periodic reviews and 3 ad-hoc replacements (PVF 2013, OGC 2015, DGC 2026).
  - It has 30 members on every session from the launch on.
  - It matches all 32 full baskets printed in sources (seed `vn30_baskets`; 9 of them are HOSE's own lists).
  - Weakest link: the 2013-H2 removal of PNJ and DIG is unverified, though implied by the baskets on either side.
- **Banks:** seed `bank_spells` lists 29 banks with every exchange spell in the study period, including Habubank (HBB, merged into SHB 2012) and PVcomBank (PCB, UPCoM from 2026-08-12). Excluded as never listed: Southern Bank, MHB, BaoViet Bank. PVF (a finance company) is not a bank.
- **Universe** (`research_universe_daily`): VN30 members as of each date, plus every bank during its listing/registration spells, on each HOSE session 2012-01-03..2026-11-20.

**Known gaps** (seed `known_price_gaps`; tests exclude only these):
- VN30: HVG and PVF have no usable CafeF history (0.9% of 110,610 member-days).
- Banks: CafeF's bulk archive drops history from before an exchange move. ACB and SHB on HNX, the UPCoM years of VIB, LPB, NAB, BAB, BVB and VBB, and all of HBB are missing (about 11,000 bank-days).

**Open**

- Whether banks that traded only on UPCoM count as "listed banks" (author's decision pending).
- Whether to fill the gaps from CafeF's per-ticker history (proposed).
