# Final run inputs (frozen 2026-11-26)

| Item | Value |
|---|---|
| Snapshot | `1f0c80b50427479e` (label `final`, see `research/snapshots.md`) |
| Code at the freeze | `2d9966b` |
| Labels | `research/paper1/runs/20261126T052329Z-labels-1f0c80b50427479e` |
| Features, k = 2 (main) | `research/paper1/runs/20261126T052338Z-features-1f0c80b50427479e-k2` |
| Features, k = 1.5 | `research/paper1/runs/20261126T052339Z-features-1f0c80b50427479e-k1_5` |
| Features, k = 3 | `research/paper1/runs/20261126T052341Z-features-1f0c80b50427479e-k3` |
| Protocol | `research/paper1/FINAL_RUN_PROTOCOL.md` (D-026), amended by D-027 |
| Runbook | `docs/runbooks/paper1-final-run.md`, section 4b (one large instance) |

## Gates (D-024)

| Gate | Status |
|---|---|
| Block E complete, with 2012–2016 values confirmed | done: D-023 clarifications 9–10 (1,151 of 1,195 bank-quarters) |
| News crawl and mentions | done: 100% coverage, 2012–2026 |
| GPR file | done: runs to 2026-11-23; rows after the cutoff are not used |
| Leakage audit, pipeline | done: `audits/2026-11-26-pre-freeze-leakage.md`, D-025 |
| Leakage review, runner | done: D-026 clarifications |
| Design review | done: D-027 |
| Full dbt build | done: 131/131, including the look-ahead tests |
| Freeze | done: `1f0c80b50427479e` |
| Labels and features from the freeze | done: the k = 2 dataset is identical to the development one |
| User's go-ahead | **pending** |
