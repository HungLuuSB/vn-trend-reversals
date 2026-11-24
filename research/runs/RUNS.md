# Run log

Every run, including superseded ones (CLAUDE.md: report all runs, not just the best). Run
folders under `research/runs/` are not in git; this log is.

| Run | Snapshot | Git commit | What | Status |
| --- | --- | --- | --- | --- |
| `20261124T081010Z-labels-b536ec69488162e0` | `b536ec69488162e0` | `cf458cb` | swing labels + survival rows, k = 2 / 1.5 / 3 | superseded: censoring at the study end was labelled `data_end` instead of `end_of_sample`; the labels and the rows themselves are identical to the next run |
| `20261124T081044Z-labels-b536ec69488162e0` | `b536ec69488162e0` | see `config.json` | swing labels + survival rows, k = 2 / 1.5 / 3 | current. k = 2: 139,241 rows, 88 stocks, 13,980 reversals in the study period, median swing age at reversal 26 days, 26.3% of rows reverse within 5 days |
