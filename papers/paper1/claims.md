# Paper 1 claims map

Every claim the paper will make, the evidence that will support it, and its current status. A claim with no evidence is cut or stated as a hypothesis (research-paper-writing skill). The status column must say **final** before a claim enters the abstract or introduction.

Status codes:
- **dev:** supported in development years 2012–2016 only. It goes into the paper as a pre-registered expectation, never as a result.
- **final:** confirmed by the single final walk-forward run on the frozen snapshot (D-024).
- **lit:** a literature claim, verified in `research/literature/NOTES.md` and `refs.bib`.
- **design:** a property of the method, shown in Section 4 or the code.

| # | Claim | Evidence (table / figure / test) | Status |
|---|---|---|---|
| C1 | Reversal timing of volatility-scaled swings is predictable out of sample beyond Kaplan–Meier (H1). | Pooled and per-year Uno C, IBS, td-AUC with paired bootstrap CIs; shuffled-label control ≈ 0.5 | dev (Findings 11–12: C ≈ 0.60 vs 0.50) |
| C2 | Most of that predictability comes from swing mechanics and local market features. | M vs A–C vs A–D; D-015 decomposition | dev (Findings 13–14) |
| C3 | Features beyond the mechanical baseline improve ranking, but not on both metrics. | ABC − M: C and IBS intervals (D-016 rule) | dev (Finding 14: C only) |
| C4 | Overnight global information does not improve reversal timing (H2 not supported). | Block-D ablations: additive, direction-specific, trees, per feature, bank-specific | dev (Findings 12, 15–17, 20) |
| C5 | Swing age adds nothing once the distance to the threshold is known; age-only duration dependence reflects distance. | D-019 nested comparison; life table by direction | dev (Finding 18) |
| C6 | Global sensitivity did not rise after the upgrade announcement (H4). | Post-2025-10-07 interaction, placebo dates | not yet tested (final run only) |
| C7 | The predicted hazard is not profitable after costs (H5). | Sharpe, drawdown, deflated Sharpe vs B&H and fixed DC | dev (Finding 19: not supported) |
| C8 | Bank fundamentals and news attention beat the mechanical baseline but add nothing beyond local market features. | D-023 comparisons on bank rows; OCR-only robustness | dev (Finding 22) |
| C9 | The neural hazard improves calibration (IBS) but not ranking. | D-022 comparisons | dev (Finding 21) |
| C10 | Survival analysis of daily index runs failed out of sample; our unit differs. | Yao et al. (2005), Fig. 3 | lit |
| C11 | Prior duration-dependence evidence is in-sample and index-level, with an age-only hazard. | Lunde & Timmermann (2004); Zakamulin (2023) | lit |
| C12 | Prior ML for DC reversals ignores censoring and uses fixed thresholds. | Adegboye & Kampouridis (2021) | lit |
| C13 | Volatility scaling makes swings comparable across stocks, allowing pooling. | θ = k·ATR20/P definition; swing-duration distributions by stock (descriptive table) | design (table to be generated) |
| C14 | No feature uses information that was not public at the 09:00 decision time. | `available_at_utc` on every value; dbt test `no_feature_after_decision_time`; leakage audit | design (audit due before the freeze) |
| C15 | Every reported number is reproducible from snapshot hash X and commit Y. | `research/snapshots.md`; `generated/numbers.tex` provenance header | design (after the freeze) |
| C16 | Any predictability beyond the label mechanics survives a flexible mechanical model (M_flex) and a model-free random-walk null (RW). | H1-mech primary: ABCx − M_flex and ABCx − RW, year-stratified, 1,000 resamples | not yet tested (final run only; RW dev check: C 0.597, descriptive) |
| C17 | The year-stratified metrics avoid rewarding differences in reversal rates between years. | Definition, eq. (stratc); pooled vs stratified reported side by side | design |
