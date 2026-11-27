# Predictable but Mostly Mechanical: Survival Forecasts of Trend Reversals in Vietnamese Stocks

Code, design record and paper sources for the study by Thai Hung Luu and Nhat Hao Pham Ngo.

The paper asks when a price swing of a Vietnamese stock ends, and how much of the answer can be
forecast with what was public before the market opened. Swings are volatility-scaled
directional-change swings (threshold 2 × ATR20 / price) of VN30 members, taken as of each date,
and all listed banks, 2012–2026. Landmark survival models are designed on 2012–2016 and tested
once, walk-forward, on 2017–2026. Reversal timing is predictable out of sample, but most of the
skill is mechanical: the distance to the reversal threshold alone accounts for about 88% of the
gain in the concordance index.

## What is here

| Path | Contents |
| --- | --- |
| `src/vnbank/` | All Python logic: ingestion clients, the directional-change labeller, features, models, evaluation, the final run and the paper-number builder |
| `dbt/` | ClickHouse models, point-in-time tests (including `no_feature_after_decision_time`) and curated, sourced reference seeds |
| `research/paper1/DECISIONS.md` | The dated decision log: every design choice, recorded before it was used |
| `research/paper1/runs/RUNS.md` | Every run, including failed and superseded ones, with its code version and data snapshot |
| `research/paper1/FINAL_RUN_PROTOCOL.md` | The protocol of the single run on the test years |
| `research/paper1/COMMIT_MAP.md` | Old → new commit ids (see below) |
| `papers/paper1/` | LaTeX sources; every number comes from `generated/`, written by code |
| `tests/` | Unit tests, including hand-built price series with known reversals |

## Data

No market data are in this repository. Daily prices come from CafeF and Yahoo Finance, the VIX and
US Treasury yields from FRED, and the geopolitical risk index from Caldara and Iacoviello (2022).
The CafeF and Yahoo Finance data cannot be redistributed; FRED and the risk index are public. All results come from one frozen data
snapshot, `1f0c80b50427479e`. The data, including the extracted bank ratios, are available from the
corresponding author on reasonable request, subject to the providers' terms.

## Reproducing

Requirements: Linux, Docker with Compose v2 and [uv](https://docs.astral.sh/uv/) (Python 3.12).

```bash
uv sync
cp .env.example .env                        # fill in local passwords
docker compose --profile research up -d     # ClickHouse, SeaweedFS (S3 raw layer), PostgreSQL
uv run python -m vnbank.ingestion.market.cafef_ingest   # raw downloads, stored before parsing
uv run python -m vnbank.ingestion.market.cafef_load
cd dbt && uv run --env-file ../.env dbt build && cd ..
uv run python -m vnbank.research.swings.build --snapshot <id>
uv run python -m vnbank.research.survival.features.assemble --snapshot <id> --labels-run <dir>
uv run python -m vnbank.research.survival.report         # paper numbers from the logged runs
uv run pytest
```

Re-downloading gives today's version of the providers' files, which may differ from the frozen
snapshot. With the snapshot itself, the labels, features and every reported run can be rebuilt
exactly.

## Commit ids

The history of this repository was rewritten once, on 27 November 2026, to remove material
belonging to a separate, unpublished paper that shared the repository. The code of this paper was
not changed, but commit ids were. Run folders and `RUNS.md` record the original ids; look them up in
`research/paper1/COMMIT_MAP.md`.

## Licence and citation

Code: MIT (see `LICENSE`). The paper text in `papers/` and the proposal in `docs/proposals/` are
© the authors, all rights reserved. To cite the software, see `CITATION.cff`.
