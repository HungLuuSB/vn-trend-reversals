# Paper 1 glossary

One term, one meaning, used consistently in the paper. Acronyms are defined at first use in the main text.

| Term | Meaning in this paper |
|---|---|
| Swing | A price move between two directional-change confirmations; it starts at a confirmed extreme and ends when the price reverses by θ from the next extreme. |
| Directional change (DC) | The labelling rule: a reversal is confirmed when the price moves θ against the running extreme. |
| θ (threshold) | k × ATR20 / price, computed on trailing data only; k = 2 in the main design, 1.5 and 3 in robustness. |
| ATR20 | 20-session average true range, from adjusted prices used only as a ratio (data rule 9). |
| Swing age | Sessions since the swing's start (its last confirmed extreme). |
| swing_dist | Current distance of the price from the swing's running extreme, as a fraction of θ. |
| Reversal (event) | Confirmation of the next directional change, i.e. the end of the swing. |
| Hazard | Probability that the swing reverses within the horizon, given that it has not reversed yet. |
| Horizon | 5 sessions (main), 10 and 20 (robustness). |
| Landmark | A (swing, session) row at which a prediction is made, using only information available then. |
| Censored | A swing still open at the study end (2026-11-20 close) or at delisting. |
| Decision time | 09:00 Asia/Ho_Chi_Minh on session t+1; a feature may use a value only if it was public before it. |
| Mechanical baseline (M) | A hazard model using only swing age and swing_dist (D-016). |
| Block A–E | Feature groups: A swing mechanics, B local market, C price limits and microstructure, D overnight global, E bank fundamentals and news. |
| First release | The first published version of a bank's quarterly figure; later restatements are never used (D-023). |
| Development period | 2012–2016; used for all design work (D-012). |
| Test years | 2017–2026 (2026 partial); used only by the single final walk-forward run. |
| Uno's C | Concordance index for censored data (Uno et al. 2011). |
| IBS | Integrated Brier score with inverse-probability-of-censoring weights (Graf et al. 1999). |
| td-AUC | Time-dependent area under the ROC curve at a horizon. |
| Deflated Sharpe ratio (DSR) | Sharpe ratio adjusted for the number of trials and non-normality (Bailey & López de Prado 2014). |
