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

---

## D-005 — UPCoM banks: kept in the universe, flagged

- **Date:** 2026-11-24
- **Type:** clarification of "all listed banks" (CLAUDE.md, Paper 1)
- **Decided by:** the author (option C of three: exclude / include / include and flag), "for now"
- **State when decided:** no snapshot, no swing labels, no model.

**Decision**

- Bank-days on UPCoM, where a bank is registered for trading rather than listed, stay in `research_universe_daily` with `bank_on_upcom = true`.
- Main results use the whole universe. A robustness check repeats them without UPCoM bank-days.

**Reason**

- UPCoM is formally the market for unlisted public companies, so "listed" is ambiguous for these banks.
- Their data is also weaker: UPCoM reference prices are VWAPs that CafeF's bulk archive lacks (D-003).
- Flagging keeps both readings available without choosing one in advance.

**Affected:** ABB, PGB and SGB (UPCoM for their whole study-period spell); KLB (to 2026-01-06); VAB (to 2025-07-09); and the UPCoM years of VIB, LPB, NAB, BAB, BVB and VBB once filled. PCB is UPCoM from 2026-08-12.

**Revisit** before the final walk-forward run. The author said "for now".

---

## D-006 — Fill bulk-archive gaps from CafeF per-ticker history; VWAP-based reference prices

- **Date:** 2026-11-24
- **Type:** data-source extension (author approved "fill the gaps", 2026-11-24)
- **State when decided:** no snapshot, no swing labels, no model.

**Decision**

1. **Gap fills.** Inside the gaps documented in seed `known_price_gaps`, `prices_daily_raw` uses CafeF's per-ticker history (`price_source = 'cafef_ticker'`) and the gap's true exchange. Elsewhere it keeps the bulk archive. Bulk rows inside a gap with no per-ticker row stay, relabelled with the true exchange.
2. **VWAP references** (exchange rule `vwap_session`: UPCoM, and HNX before 2012-03-26). The reference price = previous session's matched value / matched volume, adjusted on ex-dates and rounded to the nearest tick. It is used only when both ends of the VWAP's rounding interval (± 0.005 bn VND / volume) round to the same tick; otherwise the reference stays `ref_not_reconstructable`. Rule confidence is "unverified": the exchange's VWAP rounding rule is undocumented (D-003).

**Evidence**

- **Overlap:** where both sources cover the same stock-day (8,251 days, 12 tickers, 2012–2026), open, high, low, close and volume agree on **100%** of days.
- **Fills:** 13,055 rows kept, 2 rejected (high < low).
- **Coverage, study period:** banks 83% → **99.0%** of bank-days; VN30 99.1% → **99.93%** of member-days.
- **Still missing:** Habubank (HBB, 2012, 155 days), which appears in neither source.
- **VWAP references:** 5,395 bank-days. 0.20% of normal, non-event days trade outside the band (HOSE prev-close rule: 0.09%).
- **Banks with computed limits:** 85.2% of bank-days. Not computable: low-volume UPCoM days whose VWAP can't be pinned to one tick, and HNX's last-15-minute VWAP period (2012-03-26..2013-07-28).

**Notes**

- **Endpoint behaviour:** the per-ticker endpoint needs an exchange filter for some stocks. ACB's HNX years come back under the default (its current exchange); BVB's UPCoM years only with `ExchangeType=UPCOM`. `FETCH_PLAN` records the filter per range.
- **Calendar:** a few per-ticker rows fall on dates that are not HOSE sessions (e.g. 2018-01-23/24 for ACB and BAB). The universe calendar is HOSE sessions, so those days are outside the universe.

---

## D-007 — How disputed corporate actions are adjudicated (pre-registered)

- **Date:** 2026-11-24
- **Type:** data-cleaning procedure. The author chose option A, checking against official notices.
- **State when decided:** no snapshot, no swing labels, no model. Written before any adjudication result is known.

**Scope.** Corporate actions on universe stock-days (`research_universe_daily`) in the study period:
1. **Disputed:** every event that `qa_corporate_actions_vs_yahoo` marks `ratio_mismatch`, `ours_only`, `yahoo_only` or `date_shift`. That is 83 events across 41 stocks as of this entry.
2. **Unconfirmed:** events on stocks or periods Yahoo does not cover (68 events, 20 stocks). These are checked mechanically first: on the ex-date, the raw return implied after the adjustment, `raw_close / raw_prev_close * adj_ratio - 1`, must lie within the exchange's daily limit for that date (D-003). Events that fail join the disputed list.

**Evidence rules**
- For each event, research agents look up the official facts with a source per fact:
  - the ex-date (ngày giao dịch không hưởng quyền);
  - cash dividend per share;
  - stock dividend / bonus ratio;
  - rights ratio and rights price.
- Source priority: exchange or depository notices (HOSE, HNX, VSD), then company disclosures, then reputable press or broker event calendars.
- The ratio is never typed by hand. It is computed by one tested formula from the verified facts and the raw previous close P: reference = (P − cash + rights_ratio × rights_price) / (1 + stock_ratio + rights_ratio), and ratio = P / reference.
- The verified facts go into seed `corporate_action_adjudications` with sources and confidence. `int_corporate_actions_final` applies them:
  - corrected ratio or date;
  - added missing event;
  - removed false event.

  An event without verified facts keeps its CafeF-inferred value and is flagged `unadjudicated`.
- No adjudication may consider returns, swings or model results. The only inputs are corporate-action facts and raw prices around the ex-date.

---

## D-008 — Two judgement calls from adjudication

- **Date:** 2026-11-24
- **Type:** data-cleaning clarifications, made while applying D-007 and before any outcome is examined.

1. **Economic adjustment even where the exchange did not adjust.**
   - MBB 2016-03-09 distributed 0.25% extra shares from a merger swap, and HOSE did not adjust the reference price.
   - Adjusted prices (`prices_daily_adjusted`) apply every distribution that changes value per share, so the ratio here is 1.0025.
   - The same ratio also enters `prices_daily_limits`, which makes that day's computed reference 0.25% lower than HOSE's. The difference is below one tick for MBB's price level then and has no practical effect.
2. **Exchange-transfer artifacts.**
   - CafeF's adjusted series can jump on the day a stock moves exchange, because the pre-transfer segment is not re-adjusted for later events. KLB (2026-01-15) and VAB (2025-07-22) were confirmed as no-event days and removed.
   - No other bank has an event left on its transfer day.
   - Rule for the future: an inferred event on a transfer day is presumed to be an artifact and is queued for adjudication.

**Results of D-007**

- **Queue and sources:** all 88 queued events answered; 56 from exchange/depository notices, 32 from secondary sources.
- **Spot checks:** 3 of 3 passed against the original HOSE PDFs (TPB 2018, VIB 2020, MWG 2025).
- **Who was right:**
  - CafeF-inferred event right, Yahoo wrong: 64.
  - Yahoo right, ours wrong: 17.
  - Both wrong: 7.
- **Final universe events:** 82 adjudicated, 558 inferred.
- **Agreement with Yahoo:** 85.7% → 88.6%. Most remaining differences are known Yahoo errors (rights issues not recorded, wrong splits).
- **Open anomaly:** VBB 2021-06-10. The verified event is a 14% stock dividend, but the price fell by more, so that week of price data is suspicious. It is left as is and flagged here.

---

## D-009 — Proposal alignment: survival setup, global series, exclusions, scope

- **Date:** 2026-11-24
- **Type:** clarification of the pre-specified design against `docs/proposal.md` (now in the repo), approved by the author
- **State when decided:** no snapshot, no swing labels, no features, no model.

**1. Swing and survival definition** (proposal, Methodology 1–2; adopted exactly)

- **Threshold:** θ(i,t) = k · ATR20(i, t−1) / P(t−1), using yesterday's ATR and price. k = 2 is the main setting; 1.5 and 3 are robustness checks. Prices are adjusted closes, and days that close at the price limit are flagged (`prices_daily_limits`).
- **Up-swing reversal:** the first day t with P_t ≤ M_t (1 − θ), where M_t is the running maximum close since the last confirmed trough. Down-swings mirror this.
- **Survival rows:** one row per stock and trading day inside a swing not yet confirmed as reversed.
  - Time scale: swing age in trading days.
  - Event: the next confirmed reversal.
  - Right-censoring: end of sample (D-001), the stock leaving the universe, or a trading halt.
- **Reporting:** a discrete-time hazard, giving P(reversal within 5 / 10 / 20 trading days) and the median remaining life.

**2. Global series** (proposal, global data table), with three source changes for point-in-time correctness

| Series | Proposal source | Used | Why |
| --- | --- | --- | --- |
| Brent | FRED `DCOILBRENTEU` | Yahoo `BZ=F` (ICE Brent futures) | EIA spot assessments reach FRED with a lag of days; futures are public at the close |
| USD/CNY | FRED `DEXCHUS` | Yahoo `CNY=X` | Fed H.10 is released weekly |
| US 10-year | FRED `DGS10` | FRED `DGS10`, with availability set to when the value is actually first published | Fed H.15 posts it the next afternoon; the time to use is verified and recorded in the series seed |

All other series as in the proposal:
- Yahoo: `^GSPC`, `^IXIC`, `DX-Y.NYB`, `GC=F` (roll handling recorded in the seed), `^HSI`, `000300.SS`, `VND=X`.
- FRED: `VIXCLS`.
- The Caldara–Iacoviello daily GPR file, with a fixed, conservative publication lag recorded in the seed.

Availability rules:
- Each series' `available_at_utc` follows its market's close (or its release time) in its own time zone, with daylight saving handled by the time-zone database (CLAUDE.md rule 3).
- When HOSE is closed, global features use the cumulative change since the last Vietnamese session (rule 8).

**3. "Stocks with fewer than 250 trading days" (proposal, exclusions):** read point in time.
- A stock-day enters the sample only if the stock has at least 250 trading days of price history before that date.
- The reading "fewer than 250 days in total" is rejected: it depends on whether the stock later survives.

**4. Scope.**
- Feature blocks A–D are built first.
- Block E (bank fundamentals, news counts) is deferred until models run on A–D. It needs the platform's PDF pipeline, and the proposal uses it only for the bank subsample.
- Block C needs VN-Index history and foreign flows; if no free history of foreign flows exists, the series is dropped, as the proposal's risk table allows.

**5. Price limits.** The proposal's text states today's limits (±7 / 10 / 15%). The dated schedule in D-003 (HOSE ±5% and HNX ±7% before 2013-01-15; UPCoM ±10% before 2015-07-01) governs, and the paper's text should state it.
