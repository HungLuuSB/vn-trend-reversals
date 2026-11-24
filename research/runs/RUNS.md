# Run log

Every run, including superseded ones (CLAUDE.md: report all runs, not just the best). Run
folders under `research/runs/` are not in git; this log is.

| Run | Snapshot | Git commit | What | Status |
| --- | --- | --- | --- | --- |
| `20261124T081010Z-labels-b536ec69488162e0` | `b536ec69488162e0` | `cf458cb` | swing labels + survival rows, k = 2 / 1.5 / 3 | superseded: censoring at the study end was labelled `data_end` instead of `end_of_sample`; the labels and the rows themselves are identical to the next run |
| `20261124T081044Z-labels-b536ec69488162e0` | `b536ec69488162e0` | see `config.json` | swing labels + survival rows, k = 2 / 1.5 / 3 | current. k = 2: 139,241 rows, 88 stocks, 13,980 reversals in the study period, median swing age at reversal 26 days, 26.3% of rows reverse within 5 days |
| `20261124T081749Z-labels-b536ec69488162e0` | `b536ec69488162e0` | see `config.json` | labels + survival rows, k = 2, with `end_date` (needed for purging) | current input to features; rows identical to the k = 2 run above |
| `20261124T081754Z-features-b536ec69488162e0-k2` | `b536ec69488162e0` | see `config.json` | dataset: survival rows + blocks A-D (139,241 rows) | current |
| `20261124T081907Z-walkforward-dev-ABCD` | `b536ec69488162e0` | see `config.json` | dev inner CV 2014-16 (inside 2012-16 only): KM, logistic hazard, shuffled control | superseded (D-013): hazard chained with features held fixed was badly calibrated (IBS worse than KM) |
| `20261124T082109Z-walkforward-dev-ABCD` | `b536ec69488162e0` | see `config.json` | as above, landmark hazard (D-013) | superseded: shuffled control used one seed (2015: 0.460, noise) |
| `20261124T082643Z-walkforward-dev-ABCD` | `b536ec69488162e0` | see `config.json` | as above, shuffled control over 10 seeds | current. Uno C (tau 20): KM 0.500 / hazard 0.595, 0.591, 0.608 (2014/15/16); shuffled mean 0.505, 0.497, 0.500; IBS hazard < KM in every fold; td-AUC at 5 days 0.67-0.69; no warnings |
