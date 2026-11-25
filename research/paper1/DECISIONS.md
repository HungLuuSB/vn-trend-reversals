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

---

## D-010 — Shanghai Composite replaces the CSI 300

- **Date:** 2026-11-24
- **Type:** data-source substitution (proposal, global data table); the author chose option A of three
- **State when decided:** no snapshot, no labels, no model; no feature has been examined against outcomes.

**Decision.** Feature block D uses the Shanghai Composite index (Yahoo `000001.SS`, series `sse`, close 15:00 Asia/Shanghai) as its mainland-China equity series, in place of the CSI 300 (`000300.SS`).

**Reason.**
- Yahoo returns no price history for the CSI 300 under either symbol (`000300.SS`, `399300.SZ`; checked 2026-11-24).
- The Shanghai Composite is mainland China's other headline index, available from the same source with the same timing.
- Rejected alternatives: a separate, untested CSI 300 source; dropping the mainland series and leaving the Hang Seng as the only China signal.

**Consequence.** The paper's data section names the Shanghai Composite and states the reason.

---

## D-011 — Swing-labeller details the proposal leaves open (pre-registered)

- **Date:** 2026-11-24
- **Type:** clarification of `docs/proposal.md` Methodology 1–2, made before the labeller runs on any real data. The author delegated these choices ("do what you think is best") and can revisit them; any change gets a new entry before the main run.

1. **ATR20:** the simple average of the last 20 true ranges, TR_t = max(H_t, C_{t−1}) − min(L_t, C_{t−1}), on adjusted prices. Wilder's smoothing is not used; the proposal says "trailing 20-day average true range". θ(t) uses ATR20 and the close of day t−1, so the first threshold exists on a stock's 22nd trading day.
2. **Start and extremes.**
   - Before the first confirmed reversal, the running maximum and minimum are both tracked from the first day with a threshold, and the first confirmation in either direction starts the first swing.
   - After a confirmed down-reversal, the new down-swing's running minimum is tracked from the peak (the date of the up-swing's maximum) onward. Up-swings mirror this from the trough.
3. **Swing age (time scale).**
   - Main: trading days since the swing's starting extreme (true age; H3).
   - A swing becomes known only at its confirmation, so its survival rows start at that age: delayed entry / left truncation, handled by the models.
   - Age since confirmation is also stored, for a robustness check.
4. **Rows and event timing.**
   - A row (stock, t) describes the state after the close of day t and is used at the 09:00 decision on the next session.
   - Rows run from the confirmation day of the swing's start to the day before its reversal is confirmed. The event is the confirmation, at the close of a later day.
   - "Reversal within h days" means confirmation within the next h trading days of that stock.
5. **Censoring** (besides the end of sample, D-001):
   - **Universe exit:** censored at the last day the stock is in `research_universe_daily`.
   - **Halt:** a gap of ≥ 5 consecutive HOSE sessions without a price; censored at the last day before the gap. Shorter gaps are days without trades, and the swing continues across them.
6. **Exclusions:** rows need ≥ 250 prior trading days of the stock's own price history (D-009).

---

## D-012 — Foreign flows, gold rolls, D-011 review; development stays inside the training window

- **Date:** 2026-11-24
- **Type:** data and feature choices. The author replied "proceed" to recommendations and had earlier delegated ("do what you think is best"); each item is reversible by a new entry.
- **State when decided:** snapshot dev-v1 and labels exist. No feature has been computed against outcomes and no model fitted.

1. **Foreign net flows (block C).**
   - CafeF lacks them on 570 sessions, mostly 2019-04 to 2021-07.
   - Excluded from the main specification. A robustness run adds them with a missing indicator.
   - Reason: the gap coincides with the COVID period, so an indicator could act as a period dummy.
2. **Gold roll days.** Gold's return is set to missing in `gold_roll_window`. A continuous front-month series can jump when the contract rolls; the model's missing-value handling (fitted inside the training window) applies.
3. **D-011:** kept unchanged.
4. **Where development is evaluated.**
   - Until the final walk-forward run, every evaluation (Kaplan–Meier baseline, shuffled-label control, model checks, tuning) uses only purged, embargoed inner cross-validation inside the first training window, sessions up to 2016-12-31.
   - Test years 2017–2026 are not evaluated until the final run (CLAUDE.md research rules). The runner refuses test years unless run as the final run.

---

## D-013 — Logistic hazard fitted by landmarking (implementation correction)

- **Date:** 2026-11-24
- **Type:** correction of how the proposal's discrete-time logistic hazard is implemented. The model class and features are unchanged.
- **State when decided:**
  - One development run exists: `20261124T081907Z-walkforward-dev-ABCD`, inner folds 2014–2016 inside the training window only.
  - Its hazard model ranked reasonably (Uno C ≈ 0.60) but was badly calibrated: predicted P(reversal within 5 days) by decile ran 0.02–0.81 against 0.15–0.58 observed, and its integrated Brier score was worse than Kaplan–Meier's.
  - No test year has been evaluated.

**Problem.** The first implementation predicted h-day survival by chaining the one-day hazard while holding all features at their day-t values and advancing only the age. The strongest features describe the current position, e.g. the distance to the reversal threshold, so holding them fixed for h days exaggerates both high and low risk.

**Decision: landmarking.**
- Each row (stock, t) is expanded into steps s = 1 … min(duration, 20). The target at step s is 1 if the reversal is confirmed exactly s trading days after t. Features are fixed at their day-t values, and the step s enters as a covariate (one indicator per step).
- The model then estimates the hazard s days after a prediction made on day t, which is how it is used: S(h | x_t) = ∏_{s ≤ h} (1 − h(s | x_t)).
- Each day remains a new prediction, as the proposal states.
- Censored rows contribute their steps up to censoring.

**Shuffled-label control.** The outcome pairs (duration, event) are permuted across training rows before expansion, so the outcome distribution is kept and its link to the features is broken.

**Not changed:** features, folds, purging, embargo, metrics. The earlier run stays in the run log as superseded.

---

## D-014 — Development model comparison: tuning, models, ablation, bootstrap (pre-registered)

- **Date:** 2026-11-24
- **Type:** evaluation protocol for the development phase, written before these runs.
- **State when decided:**
  - Current dev results: landmark logistic hazard with fixed settings, C ≈ 0.59–0.61 (D-013).
  - No tuning has been done and no other model fitted.
  - No test year evaluated.

**Scope:** inside the first training window only, as in D-012. Outer folds validate 2014, 2015 and 2016, each with an expanding training window from 2012, purge, 20-session embargo, and validation labels censored at 2016-12-31.

**Tuning.**
- Nested: inside each outer fold's training data, the last full year before the fold is the inner validation year, with the same purge and embargo; the rest is inner training.
- Hyperparameters are chosen by the lowest inner integrated Brier score (IPCW, times 1–20) and the model is refitted on the full outer training data.
- Grids:
  - Logistic hazard (landmark, D-013): C ∈ {0.01, 0.1, 1}, l1_ratio ∈ {0, 0.5}.
  - Gradient-boosted discrete-time hazard (same landmark expansion, histogram gradient boosting): learning rate ∈ {0.03, 0.1}, max leaf nodes ∈ {15, 31}, 300 iterations, L2 = 1.
  - Cox proportional hazards on time since the prediction day (ridge): alpha ∈ {1, 10, 100}.
  - Random survival forest: min samples per leaf ∈ {50, 200}, 100 trees, sqrt features.
- For fitting only (not for metrics), durations beyond 21 days are censored at 21; horizons of interest are ≤ 20.
- Every model uses median imputation and standardisation fitted on its training rows.

**Comparisons reported**, all on the same validation rows:
1. Each model against Kaplan–Meier (Uno C at τ = 20, integrated Brier score).
2. **Ablation for RQ2:** the tuned logistic hazard on blocks A–C against A–D, as paired differences.
3. Shuffled-label control for the logistic hazard (mean of 10 seeds).

**Uncertainty.**
- Paired moving-block bootstrap over validation trading dates: blocks of 20 sessions, 200 resamples, the same resamples for every model.
- 95% percentile intervals are reported for each metric and for each paired difference, per fold and pooled over the three folds.

**What will not be done in development:** choosing the main specification by test-year performance, or reporting test years.

## D-015 — Decomposing the short-horizon signal: nested feature sets (pre-registered)

- **Date:** 2026-11-24
- **Type:** development analysis, written before running it.
- **State when decided:**
  - D-014 is done (run `20261124T083349Z-devcompare`).
  - Logistic hazard A–C: pooled Uno C 0.604; td-AUC 0.686 at 5 days and 0.591 at 20 days.
  - No test year evaluated.

**Question.** How much of the short-horizon skill comes from swing age alone, and how much do the other swing-state, stock and local-market features add?

**Design.** Same folds, purge, embargo, dev censoring and nested tuning as D-014. The model is the logistic hazard only, with its D-014 grid. Four nested feature sets:

1. `AGE`: `swing_age`, `log_age`;
2. `A`: block A (swing state);
3. `AB`: blocks A and B (stock technicals);
4. `ABC`: blocks A, B and C (local market). Block D is left out, given D-014.

Each set is tuned separately and reported against KM, with Uno C (τ = 20), IBS and td-AUC at 5, 10 and 20 days.

**Paired differences** use the D-014 bootstrap (blocks of 20 sessions, 200 resamples), per fold and pooled:
- A − AGE;
- AB − A;
- ABC − AB;
- ABC − AGE.

**Interpretation rule, fixed in advance.** If `AGE` reaches at least 80% of the ABC skill above chance at 5 days, i.e. td-AUC(AGE) − 0.5 ≥ 0.8 × (td-AUC(ABC) − 0.5), the short-horizon result is reported as mainly a swing-age (duration-dependence) effect, not a feature effect.

**What does not change:** the main specification. This is descriptive only.

**Addendum (2026-11-24, after the D-015 run, before this check).**
- The run found that block A carries almost all the skill.
- Descriptive follow-up: each block-A feature used alone as a raw risk score, with no fitting. Report the 5-day td-AUC on the pooled development validation rows (2014–2016); a feature scoring below 0.5 is flipped and its sign reported.
- This only describes where the signal sits. It does not change the model or the feature sets.

## D-016 — Mechanical baseline for incremental claims (approved by the user 2026-11-24)

- **Date:** 2026-11-24
- **Type:** change to how the pre-specified design is evaluated. Labels, features, splits, test years and the main model are unchanged.
- **Why:** D-015 found that `swing_dist` alone reaches a 5-day td-AUC of 0.671 against 0.686 for the full local model. It measures how far the price has already retraced toward the confirmation trigger, so part of the measured predictability follows from the label definition itself. Comparing only with Kaplan–Meier would overstate behavioural predictability.
- **State when decided:** development runs only (D-014, D-015); no test year evaluated.

**Mechanical baseline (M).** The landmark logistic hazard (D-013) on `swing_age`, `log_age` and `swing_dist`, tuned on the D-014 grid the same way as every other model.

**How each question is judged:**
- **RQ1:** H1 is still tested against Kaplan–Meier, as proposed. Predictability *beyond the label mechanics* is claimed only if the full local model (A–C) beats M: paired bootstrap intervals for the C-index and IBS differences that exclude zero. Both comparisons are reported.
- **RQ2 (primary, unchanged):** A–D against A–C. Secondary: M + D against M.
- **RQ3:** the swing-age hazard shape is reported unconditionally and conditional on `swing_dist` (within M). An age effect is claimed only if it survives the conditioning.
- **RQ5:** an exit rule driven by M's predicted hazard is added as a benchmark strategy, next to buy-and-hold and the fixed directional-change rule.
- Kaplan–Meier stays in every table.

**Development check, before any test year:** same folds, purge, embargo and bootstrap as D-014.
- Feature sets: M, M+B, M+B+C, M+D, A–C, A–D.
- Paired differences: (A–C) − M, (M+B) − M, (M+B+C) − (M+B), (M+D) − M, (A–D) − (A–C).

## D-017 — Direction-specific effects for blocks B–D (specification correction, pre-registered)

- **Date:** 2026-11-24
- **Type:** correction to how features enter the linear models. Labels, θ, horizon, decision time, splits and test years are unchanged.
- **Why.** Every return and change feature in blocks B, C and D (e.g. `ret_1`, `vnindex_ret`, `spx_ret`, `vix_chg`) enters with its raw sign, and `swing_dir` is a separate column. A linear hazard therefore gives a feature the *same* effect on up-swings and down-swings. H2 is directional: "US equity falls and VIX jumps raise the hazard that an *up*-swing ends", so the same fall should *lower* the hazard that a down-swing ends. Under the D-014 specification these opposite effects cancel. That specification cannot test H2 and may explain the null block-D ablation. Block A is already expressed relative to the swing (`swing_move`, `swing_dist`) and is unchanged.
- **State when decided:**
  - D-014, D-015 and D-016 (running) are development only; no test year evaluated.
  - No direction-interacted model has been fitted.

**Specification.**
- Every feature x in blocks B, C and D enters both as x and as `swing_dir` × x (column `<x>_xdir`), giving direction-specific slopes.
- Missing values stay missing and are median-imputed inside each training window, as before.
- This becomes the specification of the linear models (logistic hazard, Cox) for the final run. The D-014 additive results stay reported.

**Development check** (D-014 protocol, logistic hazard tuned on the D-014 grid).
- Feature sets:
  - `M` (D-016);
  - `MBC`: M + B + C, additive;
  - `MBCx`: M + B + C with interactions;
  - `MBCDx`: MBCx + D with interactions;
  - `ABCx`;
  - `ABCDx`.
- Paired differences:
  - MBCx − MBC: does direction matter;
  - ABCDx − ABCx: RQ2, primary from now on;
  - MBCDx − MBCx: RQ2 over the mechanical baseline;
  - ABCx − M: RQ1 beyond the mechanics, D-016.
- **Tree check** (separate run, to keep each job under an hour): the gradient-boosted hazard on raw A–C vs raw A–D. Trees can form direction interactions themselves, so this tests RQ2 without the linear specification.

**Guard against specification search.** This is the only change to the block-D specification made after seeing development results. It follows directly from the stated wording of H2. If D still adds nothing under it, the null stands and no further D specifications will be tried on development data, except the pre-specified bank × global interactions of RQ2.

## D-018 — Per-feature attribution for block D, including gold vs. geopolitical risk (pre-registered)

- **Date:** 2026-11-24
- **Type:** descriptive attribution, written before running. It does not select features.
- **Why.** The user asked whether gold is noise or a genuine channel ("a geopolitical barometer").
- **Data note.** Block D uses COMEX front-month gold futures (`GC=F`), not spot (LBMA). Their daily returns are almost identical. Spot benchmarks are licensed, and the FRED LBMA series is discontinued. Roll-day returns are already NaN (D-012). No source change.

**Design.** Runs after D-017, on the D-017 specification (`ABCDx`), development folds as in D-014.
1. **Leave one feature out.** For each of the 14 block-D features, drop x and `<x>_xdir`, refit with the hyperparameters chosen for `ABCDx` in that fold (no re-tuning), and compute the paired change in Uno C and IBS against `ABCDx`.
   - Pooled moving-block bootstrap intervals (blocks of 20 sessions, 200 resamples).
   - Holm correction across the 14 features.
   - A feature is called informative only if its Holm-adjusted interval excludes zero for IBS.
2. **Gold beyond geopolitical risk.** Compare:
   - (`ABCDx` without gold) vs `ABCDx`;
   - (`ABCDx` without gold and GPR) vs (`ABCDx` without gold).
   - Read: does gold add anything when GPR is in, and does GPR add anything when gold is out?

**Use of results.** Development results are descriptive only and do not drop features from the final specification. The confirmatory attribution is repeated once in the final run on 2017–2026.

**D-018 amendment (2026-11-24, before any D-018 run).**
- **Problem:** with 200 resamples the smallest attainable bootstrap p-value is 1/200 = 0.005. Holm across 14 features needs p < 0.05/14 ≈ 0.0036 for the first step, so no feature could ever pass. As written, the test was unable to detect anything.
- **Change:** the D-018 IBS test uses **2,000** paired moving-block resamples (blocks of 20 sessions), pooled over the dev folds. The p-value is two-sided, 2 × min(P(Δ ≤ 0), P(Δ ≥ 0)), Holm-adjusted across the 14 features. Δ = IBS without the feature − IBS of `ABCDx`, so a positive Δ means the feature helps.
- **Unchanged:** C-index differences are reported with unadjusted 95% intervals and are descriptive only. Hyperparameters per fold are those chosen for `ABCDx` in the D-017 run.
- **Compute budget (same date, before running):** Uno's C costs about 0.7 s per evaluation against 0.016 s for IBS, so C on 2,000 resamples × 16 variants would take about 6 hours. The leave-one-out table therefore reports C as point estimates only. C intervals (200 resamples) are computed only for the three gold/GPR models. The IBS test is unaffected.

## D-019 — RQ3 (do trends age?) on development data, conditional on the mechanics (pre-registered)

- **Date:** 2026-11-24
- **Type:** development analysis written before running, under the D-016 rule for RQ3: an age effect is claimed only if it survives conditioning on `swing_dist`.
- **State when decided:**
  - D-015 found that age alone has some skill: 5-day td-AUC 0.540 [0.514, 0.565].
  - Whether age adds anything once `swing_dist` is known has not been tested.
  - No test year evaluated.

**Design.** D-014 protocol (folds 2014–2016, purge, embargo, dev censoring, nested tuning), logistic hazard. Feature sets:
- `DIST`: `swing_dist` only;
- `M`: `swing_age`, `log_age`, `swing_dist`, the D-016 baseline;
- `AGE`: `swing_age`, `log_age`.

Paired differences (pooled moving-block bootstrap, blocks of 20 sessions, 200 resamples):
- **M − DIST: age given the mechanics (H3, primary);**
- AGE − KM: age unconditionally;
- DIST − KM: the mechanics alone.

**Decision rule, fixed in advance.** H3 is supported in development only if, for M − DIST, the pooled C interval lies above zero **and** the pooled IBS interval lies below zero.

**Descriptive shape** (no test, development rows only):
- the empirical share of rows reversing within 5 days, by swing-age bucket (1–5, 6–10, 11–20, 21–40, 41–80, > 80 days) within `swing_dist` terciles;
- the 5-day reversal probability predicted by M, fitted on all development rows up to 2016-12-31 with the 2016 fold's chosen hyperparameters, across the same age buckets at the median `swing_dist`.

**What does not change:** the main specification. This is descriptive and decides only what RQ3 may claim from development data. The confirmatory version is in the final run.

**Clarification (2026-11-25), descriptive table only, made before any descriptive output was seen.** `swing_dist` is exactly 0 on 34.8% of development rows: the close is the swing's new extreme. So tercile edges tie at 0 and `pd.qcut` cannot form three groups. The groups become:
- `at_extreme`: `swing_dist` = 0;
- `near` and `far`: rows with `swing_dist` < 0, split at their median (−0.41 θ).

The model-shape table and the test results do not change.

## D-020 — RQ2 bank × global interactions on development data (pre-registered)

- **Date:** 2026-11-24
- **Type:** the last block-D specification allowed on development data by the D-017 guard. The proposal (RQ2, H2) pre-specifies it: "Banks react more to rates and the dollar than other VN30 stocks".
- **State when decided:**
  - D-017, D-018 and the tree check found no detectable block-D information in 2014–2016.
  - Development data hold 9 banks (ACB, BID, CTG, EIB, MBB, NVB, SHB, STB, VCB), about 24% of rows.
  - No test year evaluated.

**Specification.**
- Rate and dollar channels, chosen in advance from H2: `ust10_chg`, `dxy_ret`, `usdvnd_ret`.
- `ABCDx_bank` = `ABCDx` + `is_bank` + `is_bank` × each channel + `is_bank` × each channel × `swing_dir`. The direction-specific form follows D-017.

**Comparison.** D-014 protocol, logistic hazard tuned on the D-014 grid. Paired difference `ABCDx_bank` − `ABCDx` (pooled block bootstrap, blocks of 20, 200 resamples).
- **Decision rule:** H2's bank part is supported in development only if the pooled C interval lies above zero **and** the IBS interval lies below zero.
- Descriptive: per-fold results.

**Guard.** After D-020, no further block-D specification is examined on development data. Everything else about RQ2 is decided by the final run.

## D-021 — Trading test (RQ5): rules the proposal leaves open (pre-registered before any backtest code)

- **Date:** 2026-11-24
- **Type:** clarification of the proposal's economic test (Methodology, "Economic test"), written before any backtest code or result exists.
- **Why:** each open detail below could be chosen after the fact to flatter results.

**Settlement (correction to the proposal's "T+2").**
- Vietnam settled equities **T+3 until trades of 2015-12-31** and **T+2 for trades from 2016-01-04** (VSD decision of December 2015; broker notices from HSC, KIS and VNDIRECT, and Vietstock 2015-12-29).
- The cycle in force on each trade date comes from a sourced seed `dbt/seeds/settlement_cycle.csv`.
- Shares arrive on the settlement day (T+3 at 09:00; T+2 in the afternoon). Orders execute at the open, so **the earliest sell is the open of the session after the settlement day**: buy-day index + cycle + 1 sessions.

**Timing and prices.**
- Signals use information up to the close of t; orders execute at the **open of t+1** (the 09:00 decision time).
- Returns use adjusted opens (open-to-open). Fill checks use raw prices against that day's ceiling and floor (data rules 6 and 9).

**Fills.**
- A buy does not fill if the raw open is at or above the ceiling. A sell does not fill if the raw open is at or below the floor (the proposal's "no fill at limit-down"). An unfilled order is retried at the next open while its signal still holds.
- Where the limit is unknown (`limit_status != 'computed'`) the order is assumed to fill and the day is flagged. Sensitivity: no trading on such stock-days.
- Second sensitivity: a sell also fails if the day closes at the floor.
- A stock with no price on a day cannot be traded that day; the position is carried.

**Strategies** (one position at most per stock):
1. **Model exit (H5):** enter at the open after an up-swing is confirmed (`swing_dir` turns +1 at the close of t). Exit at the open after the first day on which the predicted 5-day reversal probability exceeds τ, or after the down-reversal is confirmed, whichever comes first. No re-entry within the same up-swing.
   - Model: the main linear specification, logistic hazard `ABCDx` (D-017), with that fold's chosen hyperparameters.
2. **Mechanical exit (D-016 benchmark):** the same rule with M's predictions.
3. **Directional-change exit (proposal benchmark):** same entry; exit at the open after the down-reversal is confirmed.
4. **Buy-and-hold (proposal benchmark):** hold every universe stock while it is in the universe.
   - **Universe:** point-in-time research universe stock-days that satisfy the 250-day history rule.
   - On leaving the universe, any strategy's position is closed at the next open.

**Portfolio.**
- Each day the portfolio return is the equal-weighted mean, over that day's universe stocks, of each stock's slot return: the stock's open-to-open return if held, 0 if in cash.
- Re-weighting costs are not charged, for all strategies alike. Only entries and exits pay costs.
- At the end of each evaluation year, open positions are closed at the last open, paying costs.

**Costs.** Main 0.40% round trip: 0.15% brokerage per side plus 0.10% tax on sales, so buy 0.15% and sell 0.25%. Sensitivities, with the tax kept at 0.10%:
- 0.20% total: buy 0.05%, sell 0.15%;
- 0.80% total: buy 0.35%, sell 0.45%.

**Threshold τ.**
- Grid {0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60}.
- Chosen per outer fold on the inner validation year (as in D-014 tuning), by the net Sharpe ratio at 0.40% costs. Ties go to the larger τ.
- The same procedure applies to the mechanical exit.

**Metrics.** Annualised return (252 sessions), annualised Sharpe ratio (risk-free rate 0; also reported in excess of buy-and-hold), maximum drawdown, turnover, number of trades, share of fills assumed under unknown limits.
- **Deflated Sharpe ratio** (Bailey and López de Prado 2014) with N = 16 trials: 8 τ values × 2 hazard-driven strategies.
- Paired moving-block bootstrap (20 sessions, 200 resamples) of Sharpe differences: model exit − DC exit, model exit − buy-and-hold, model exit − mechanical exit.

**Development decision rule (H5, 2014–2016 only).** H5 is supported in development only if the pooled model-exit Sharpe exceeds both benchmarks (DC exit and buy-and-hold) with paired intervals above zero at 0.40% costs. The test years are evaluated once, in the final run.

## D-022 — Neural hazard model on development data (pre-registered)

- **Date:** 2026-11-25
- **Type:** the proposal's fifth model family ("a GRU sequence encoder over the last 60 days with a logistic-hazard output layer"), specified before any neural model is fitted. The user approved the PyTorch dependency on 2026-11-25.
- **State when decided:**
  - D-014 to D-021 are done: linear, tree and forest models, and the trading test. The skill is mostly mechanical (D-016, D-019), and the global block adds nothing in any form tried (D-016 to D-020).
  - No neural model has been fitted.
  - No test year evaluated.

**Model.**
- **Sequence input** for row (stock, t): the stock's own last 60 trading days, ending with t. Four channels per day, all scale-free, computed from `prices_adjusted` (rule 9) and known at the close of that day:
  1. log close-to-close return;
  2. log(high / low);
  3. log(close / open);
  4. log(volume / mean volume of the previous 20 days).
- **Encoder:** one GRU layer (hidden size h) over the 60 days. Its last hidden state is concatenated with the row's static features at t.
- **Head:** one hidden layer (size h, ReLU, dropout 0.2), then 20 logits: the hazard at steps s = 1 … 20 after t. This is the D-013 landmark target, so S(h | x_t) = ∏_{s ≤ h} (1 − hazard_s).
- **Loss:** the discrete-time negative log-likelihood (Kvamme et al. 2019), i.e. binary cross-entropy over each row's at-risk steps (s ≤ min(duration, 20)). Durations are capped at 21 for fitting, as in D-014.
- **Preprocessing,** fitted on training rows only:
  - static features: median imputation and standardisation, as for every model;
  - sequence channels: per-channel mean and sd from the training rows' sequences, values clipped at ±10 sd, missing values set to 0 after standardisation.
- **Training:**
  - Adam, learning rate 1e-3, batch 512, training rows shuffled within each epoch (rows only; the split stays chronological);
  - CPU, a fixed seed and deterministic algorithms.
  - **Added before any run (2026-11-25):** the output layer's bias starts at the logit of the training rows' empirical hazard at each step, a Kaplan–Meier-like starting point. Reason: a unit test with a planted signal showed that from a zero bias (hazard 0.5 per step, a 97% predicted 5-day reversal) the few gradient steps in 5–15 epochs leave the network far from the data, and its ranking was even reversed.
  - CPU instead of the proposal's GPU because the model is tiny (4 × 60 inputs, ~30k training rows). This changes nothing in the model.

**Tuning** (D-014 nested protocol, chosen by inner IBS):
- h ∈ {16, 32}, weight decay ∈ {1e-4, 1e-3}, epochs ∈ {5, 15};
- tuning fits use seed 0;
- the outer refit averages the survival curves of seeds 0, 1 and 2, so a single seed's noise does not decide the result.

**Specifications** (same validation rows as D-014):
- `nn_seq_ABCD`: sequence + blocks A–D static (raw; the network forms interactions itself, as in D-017-gbm);
- `nn_seq_ABC`: sequence + blocks A–C;
- `nn_static_ABCD`: the same head on blocks A–D, no sequence;
- `ABCDx`: the D-017 logistic hazard, re-tuned here as the linear reference;
- `M`: the D-016 mechanical baseline.

**Paired differences** (pooled moving-block bootstrap, 20 sessions, 200 resamples):
1. `nn_seq_ABCD − nn_static_ABCD`: does the raw 60-day path add information beyond the hand-made features? This is the purpose of the sequence model.
2. `nn_seq_ABCD − ABCDx`: neural vs linear.
3. `nn_seq_ABCD − M`: beyond the mechanics (D-016 rule).
4. `nn_seq_ABCD − nn_seq_ABC`: RQ2 inside the neural family.

**Decision rule, fixed in advance.** A difference counts as an improvement only if the pooled C interval lies above zero **and** the pooled IBS interval lies below zero. The shuffled-label control is run for `nn_seq_ABCD` with its chosen parameters: 3 permutations, one seed each; the mean C should be ≈ 0.5. A C-index above 0.70 stops the run for a leakage audit (`too_good_c`).

**Point-in-time check.** A unit test confirms that a row's sequence is unchanged when every price after t is altered.

**What does not change:** labels, folds, purge, embargo and metrics.

## D-023 — Block E (bank fundamentals, news) on development data (pre-registered)

- **Date:** 2026-11-25
- **Type:** specification of the proposal's block E ("first-released quarterly ratios, news mention counts; bank subsample"). It is written before any block E value has been joined to an outcome. The owner approved the full CafeF news crawl and the OCR route on 2026-11-25.
- **State when decided:**
  - D-014 to D-022 are done; no test year has been evaluated.
  - Sources and their limits are in `docs/blockE-data-feasibility.md`.
  - The OCR extractor passes its sum check on every sampled 2012–2013 ACB statement. The full dev extraction (9 banks, 252 consolidated documents) is running, and its coverage is not yet known.

**Fundamentals.**
- **Document per bank-quarter (first release):**
  - the consolidated quarterly statement (`HN`);
  - for Q2 without an `HN`, the reviewed half-year statement (`HNSX`);
  - for Q4 without an `HN`, the audited annual statement (`HNKT`).
  - The parent-only statement (`M`) is used only for a bank with no consolidated statement in that quarter.
  - Later versions (reviewed, audited, restated comparison columns) are never used for features.
- **Values:** the current-period column only. NPL ratio = groups 3–5 / total customer loans (SBV classification), accepted only when the five groups sum to the printed total in both columns.
  - **Clarification (2026-11-25, before any block E value was joined to an outcome).** The first OCR pass showed three things: printed totals differ from the sum by presentation rounding (e.g. CTG Q3/2013: 345,555,671 summed vs 345,555,670 printed, million-VND rounding); OCR sometimes loses the comparison column of the total line; and "Nợ" is often misread.
  - The acceptance rule becomes:
    - the **current** column must sum to its printed total within max(5 units, 10⁻⁷ × total);
    - the comparison column must do the same **whenever its total is legible**;
    - every line after the five group rows is tried as the total line (a garbled first "Tổng" line can be followed by a clean one).
  - Labels match on their distinctive words. A misread significant digit is still rejected; a unit test pins this.
  - **Clarification 2 (2026-11-25, after the full dev OCR pass, before any block E value was joined to an outcome): unclassified rows and the denominator.**
    - Some tables print rows between group 5 and the total that are not in any SBV group: SHB's Vinashin loans awaiting resolution (2014) and MBB's repo and margin advances by its broker MBS (2014–2016).
    - **Acceptance:** such a table is accepted when the five groups **plus** at most two such rows sum to the printed total in **both** columns (the comparison total must be legible). The rows are recorded as `extra`.
    - **Denominator:** NPL ratio = groups 3–5 / the sum of the five groups (the SBV-classified loans). With no extra rows this equals the printed total to the rounding tolerance, so every value accepted under the first rule is unchanged (to ~10⁻⁷). With extra rows it keeps the ratio independent of where the table's total is drawn: MBB's 2014 annual table prints both the bank-only subtotal and the total including MBS, and the two readings gave 2.757% and 2.730%.
    - Label keys also accept "tiêu chu…" for group 1 when no other group matches ("Nợ 40 tiêu chuan" for "đủ") and "…n chú ý" for group 2 ("Nợ cén chú ÿ"). The sum check still guards every reading; unit tests pin both cases.
  - **Second pass, tried and dropped (2026-11-25).** On skewed EIB scans, tesseract misreads digits (e.g. "1,413,300" for 1.412.300) and drops rows at every resolution and layout setting tried. No parser can recover them, and the sum check rightly rejects the result.
  - **Third tier: visual transcription.**
    - **Applies to:** a first-release statement whose table the OCR parser cannot accept.
    - **Method:** the assistant reads the loan-quality table from the rendered page image.
    - **Acceptance:** the five groups must sum **exactly** to the printed total in **both** columns. This is stricter than for OCR rows, and a value that fails is not recorded.
    - **Storage:** rows go to the curated seed `dbt/seeds/loan_quality_transcribed.csv`, with the raw-layer key and page number on every row (CLAUDE.md seed exception), flagged `method = visual`.
    - **Robustness:** block E results are also reported with these rows removed.
    - **Why:** leaving these quarters missing would drop most of EIB from a 9-bank development sample. An exact two-column sum check is strong evidence of a correct reading.
- **Features** (bank rows; NaN when missing, then median-imputed like every feature):
  - `npl_ratio`: the latest available first-released value;
  - `npl_change`: the latest value minus the previous quarter's first-released value.
- **Conditional additions:** balance-sheet ratios (loan growth y/y, deposit growth y/y, loans/deposits, ROA, ROE) are added only if their extraction passes an accounting check, chosen before extraction, on at least 90% of first-release documents. The check: total assets = total liabilities + equity, to the printed precision. Otherwise they are dropped and reported as not extractable.
- **CAR is dropped:** it is not disclosed quarterly before 2020 (feasibility scout).

**Publication time** (HOSE's disclosure API is not available to this project; see the scout).
- `available_at` = the 09:00 decision time of the **5th trading session after the later of**:
  - (a) the filing deadline: quarter end + 45 days for quarterly statements, the half-year end + 45 days for `HNSX`, the year end + 90 days for `HNKT`;
  - (b) the PDF's own creation date (Asia/Ho_Chi_Minh), where present.
- The deadlines are deliberately conservative:
  - consolidated quarterly statements were due within 45 days under Circular 52/2012 (HOSE, as reported by Báo Đầu tư on 2015-02-26: https://baodautu.vn/hose-thuc-doanh-nghiep-cong-bo-thong-tin-d8443.html);
  - from 2016, Circular 155/2015 sets 20 days, extendable on request.
- The 5-session margin covers late filing after the PDF was created.
- **Robustness:** margins of 0 and 20 sessions.
- **Validation:** for each statement, the earliest CafeF article mentioning the bank and its quarterly result (from the news crawl) is compared with `available_at`. The share of statements with news earlier than `available_at` is reported. It measures how conservative the rule is; it is not used as a feature.

**News.**
- **Articles:** CafeF archive pages; publication time from the page's `pdate` timestamp (+07:00).
- **Bank aliases:** a seed (`dbt/seeds/bank_aliases.csv`) with the ticker as a whole word plus the bank's common short names, each row sourced to the bank's own name in `bank_spells.csv` or its website.
- **Mention:** an alias in the title, sapo or body.
- **Features for row (stock, t):**
  - `news_count`: articles mentioning the bank published in [decision time of t, decision time of t + 1), i.e. 09:00 on t to 09:00 on t + 1;
  - `news_rel_20`: log((1 + news_count) / (1 + mean news_count over the previous 20 sessions)).

**Clarification 3 (2026-11-25, before any block E value was joined to an outcome): implementation details the text above leaves open.**
- **Aliases.** The main `news_count` uses the strict aliases: those flagged ambiguous in `bank_aliases.csv` (e.g. "MB") are excluded. Robustness: all aliases.
- **Article identity.** Articles are deduplicated by URL; repair bundles for a window are read alongside the first bundle.
- **History for `news_rel_20`.** Counts are built for every HOSE session, so the 20-session mean does not depend on which rows are in the risk set. The value is NaN for the first 20 sessions of the crawl (January 2012).
- **Creation date.** The PDF's `CreationDate` (`pdfinfo -isodates`) is converted to its Asia/Ho_Chi_Minh date. If it is absent, the deadline alone applies; `ModDate` is never used.
  - For an archive, the latest `CreationDate` among its PDFs is used.
  - For a `.docx`, `docProps/core.xml` `dcterms:created` is used.
- **Missing documents.** CafeF's list endpoint intermittently returns an empty list. The dev download was repeated with retries (up to 8 per bank-year), so a bank-quarter is missing only if CafeF lists no document for it.

**Clarification 4 (2026-11-25, full-period download; before any 2017–2026 block E value exists): file versions.**
- From about 2022, CafeF also lists files with a suffix after the statement kind, e.g. `VCB_22Q2_BCTC_HNSX_2022-092134.pdf`. The filename parser now accepts the suffix, and the kind is still the part before it.
- When one bank-quarter has more than one file of the chosen kind (an original and a re-upload, or a corrected version), the **first release is the file with the earliest PDF creation date**. Ties, or files with no creation date, go to the unsuffixed name, then the earliest raw key.
- The precedence of kinds (HN > HNSX/HNKT stand-ins > M) does not change. Later versions are never used.

**Clarification 5 (2026-11-25, full-period download; before any 2017–2026 block E value exists): statement kind for new file names, and single-entity banks.**
- From about 2023, CafeF names many files freely, for example `20260126_-_ACB_-_BCTC_hop_nhat_Quy_04_nam_2025_….pdf`, so the filename gives no kind. For these files the kind comes from CafeF's own description of the file in the stored list reply (`Name`), with the period taken from `Time`.
  - "hợp nhất" (consolidated) gives HN, HNSX if reviewed ("đã soát xét") and HNKT if audited ("đã kiểm toán").
  - "công ty mẹ" (parent) gives M, MSX and MKT in the same way.
  - On the 1,593 listed files whose filename *does* parse, this mapping matches the filename's kind in all but two: STB Q2/2011 `KQKD_MSX`, an income statement only, and BAB Q2/2024 `MSX`, described without \"soát xét\". The filename's kind is used whenever it parses.
- **Single-entity statements.** Some banks publish one set of statements, neither consolidated nor parent-only ("Báo cáo tài chính quý …"): LPB in every year 2016–2026, PGB in 2019, ABB in 2026, and ACB once (Q4/2014, alongside an HN). For such a bank they are the full-entity report. Precedence:
  1. HN;
  2. the single-entity quarterly statement (kind `Q`);
  3. HNSX or HNKT standing in for Q2 or Q4;
  4. a reviewed or audited single-entity statement (`SX`, `KT`) standing in for Q2 or Q4;
  5. M.
  - In the development data the only case is ACB Q4/2014, where HN exists and still wins, so the D-023 development results do not change.

**Comparison** (D-014 protocol: folds 2014–2016, purge, embargo, nested tuning, logistic hazard). Fitted and evaluated **on bank rows only**:
- `ABCDx` vs `ABCDx + E`: the primary block E test;
- `M` vs `M + E`: block E beyond the mechanics.
- Paired pooled block bootstrap (20 sessions, 200 resamples).
- **Decision rule:** an improvement only if the pooled C interval is above zero **and** the IBS interval is below zero.
- **Power:** development has 9 banks (about 9,600 rows). A null result is reported as "not detected with this sample", not as "no effect".

**What does not change:** labels, folds, metrics, and blocks A–D.

## D-024 — Final snapshot freeze moved from mid-February 2027 to as soon as the pipeline is complete

- **Date:** 2026-11-25
- **Decided by:** the user ("Move the freeze to 20-11"), after the trade-offs below were explained.
- **Decision:**
  - The data cutoff is unchanged: the **2026-11-20 close** (D-001). Nothing after it enters any feature, label, outcome or estimate.
  - The final snapshot is frozen **as soon as the pipeline is complete**, instead of waiting until mid-February 2027 for the data about the study period to "settle". The target is early December 2026.
- **Why:**
  - Every feature uses only values public before its decision time, and bank figures are first-release (rules 3–5). Waiting adds nothing that was knowable before 2026-11-20.
  - Later revisions to past data (GPR revisions, restatements, re-adjusted archives) are, if anything, a form of look-ahead, so an earlier freeze is cleaner.
  - Swings still open at the cutoff are right-censored, so no prices after 2026-11-20 are needed.
- **What gates the freeze** (each step finished and logged before it):
  1. block E for all banks, 2016–2026 (OCR, visual transcription, first-release selection, D-023 clarifications 4–5), with the 2012–2016 values confirmed identical to the D-023 inputs;
  2. the 2017–2026 news crawl and mention extraction;
  3. the raw GPR file covering every US date up to 2026-11-20;
  4. the `leakage-audit` skill over the whole pipeline, and a referee-style review of the design;
  5. all tests and dbt tests passing, configs committed.
- **What does not change:**
  - the single final walk-forward run on 2017–2026 happens only once, on the frozen snapshot, and only with the user's explicit go-ahead;
  - a data problem found after the freeze reopens it as a new, documented snapshot, and every run is reported.
