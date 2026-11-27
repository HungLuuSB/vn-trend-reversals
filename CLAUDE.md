# Trend reversals in Vietnamese stocks (Paper 1)

## What this repo is

The code, design record and paper sources for *Predictable but Mostly Mechanical: Survival Forecasts of Trend Reversals in Vietnamese Stocks* (Paper 1), with the data pipeline it needs: point-in-time daily data for the VN30 members (as of each date) and all listed banks, CafeF prices into ClickHouse, dbt marts, bank statements and news for block E. Proposal: `docs/proposals/paper1-trend-reversals.md`.

The wider data platform (streaming, CDC, search, serving) and a second paper live in separate repositories. Some modules here (`documents/`, `serving/`) are placeholders from that platform.

**Study period:** sessions **2012-01-03 to 2026-11-20**, to that day's close (D-001). Nothing after the 2026-11-20 close enters features, labels, outcomes or estimates; swings still open then are right-censored.

**Research correctness beats engineering polish.** If goals conflict, stop and ask.

## Machine and environment

- Runs on an always-on Arch Linux laptop (RTX 2050 4 GB, 16 GB RAM), reached over SSH via Tailscale from a Windows desktop. Long jobs run in `tmux`, sessions named by purpose.
- Python 3.12 via `uv` only. Never use system Python or `pip install` globally: `uv add <pkg>`, `uv run <cmd>`.
- Services run in Docker Compose. RAM budget is 16 GB: start only the profile you need (`research` = ClickHouse, SeaweedFS (the S3 raw layer), PostgreSQL, Airflow once DAGs exist). MinIO no longer ships images; "MinIO" in older docs means the S3 raw layer (ADR 0001). Never start the full stack without asking.
- Cloudflare WARP must stay disconnected (it breaks Tailscale).
- Store all timestamps in UTC. Vietnam = `Asia/Ho_Chi_Minh` (UTC+7, no DST). US markets = `America/New_York` (has DST). Always use `zoneinfo`, never fixed offsets.

## Repo layout

All Python logic lives in one installable package, `src/vnbank/` (migrated 2026-11-24; the rebuilt labels and feature dataset were verified identical to the pre-migration ones). Airflow DAGs, notebooks and scripts stay thin and import from it. Items marked "planned" do not exist yet.

```
src/vnbank/
  common/          paths (repo, snapshots, runs), env (.env loading), raw_store (S3 raw layer), clickhouse;
                   planned: timeutils, logging
  ingestion/       market/ (CafeF, Yahoo, foreign flows), global_markets/ (FRED, GPR), filings/, news/
  documents/       parse/, tables/, chunk/, embed/, index/
  serving/         api/ (FastAPI), mcp/ (MCP server)
  research/
    shared/        config (paper configs), snapshot (freeze), run_meta (code version), report helpers
    swings/        directional-change labeller, risk set, label build
    survival/      features/, models/, evaluation/, walkforward, final/ (the single final run), report
airflow/dags/      thin DAG files only
dbt/               models/{staging,intermediate,marts}, tests/, macros/,
                   seeds/ (price limits, tick sizes, VN30, bank spells, global series, market events)
cdc/  quality/  monitoring/  eval/
docker/            compose.yml (profiles: research, streaming, search, monitoring), per-service configs
research/          non-code research artefacts
  snapshots.md     registry of frozen snapshot hashes
  paper1/          configs/main.yaml, DECISIONS.md, FINAL_RUN_PROTOCOL.md, audits/, runs/
papers/
  paper1/          main.tex (journal), preprint.tex, supplement.tex, sections/, refs.bib, generated/
docs/              project-summary.md, proposals/, architecture/, adr/, runbooks/, drills/
tests/             unit/ (mirrors src/vnbank), integration/ (needs Docker), fixtures/ (small hand-built series)
scripts/           one-off CLI helpers (bootstrap, backfill)
data/              git-ignored local cache; data/snapshots/<hash>/ holds frozen research snapshots
```

The dbt models keep their existing folders for now (`staging/`, `intermediate/`, `marts/` plus `universe/`, `global/`, `local/`). Paper 1's run index is `research/paper1/runs/RUNS.md`.

`runs/` folders hold config, git commit, snapshot hash and `metrics.json` per run, with no large artefacts. Notebooks are for exploration only, numbered `01_…`, and never the source of a reported result.

## Commands

```bash
uv sync                                   # install/refresh the environment
uv run pytest                             # tests
uv run ruff check . && uv run ruff format .
docker compose --profile research up -d   # minimal stack for the research
cd dbt && uv run --env-file ../.env dbt build   # models + tests (credentials from .env)
uv run python -m vnbank.ingestion.market.cafef_ingest  # download CafeF archives to the raw layer
uv run python -m vnbank.ingestion.market.cafef_load    # raw layer -> ClickHouse raw_cafef_eod
uv run python -m vnbank.research.swings.build --snapshot <id>          # labels + risk set
uv run python -m vnbank.research.survival.features.assemble --snapshot <id> --labels-run <dir>
scripts/merge-pr.sh <pr>                  # merge only after CI has registered and passed
```

## Data rules (non-negotiable)

1. **Raw is immutable.** Every download is saved to the S3 raw layer (`raw/<source>/<yyyy-mm-dd>/…`) before parsing. Never edit raw files; write new versions.
2. **Never commit market data, raw data or secrets.** No `.parquet`, `.csv` data, raw files or `.env` in git. The one exception: curated reference seeds in `dbt/seeds/*.csv` (small, hand-checked, a source on every row) are code and must be committed. API keys live in `.env` on the laptop.
3. **Every observation has `available_at_utc`**: when the value became public (market close, quote time or release time), not the date it describes.
4. **Decision time** = HOSE open, 09:00 `Asia/Ho_Chi_Minh`, on day t+1. A feature may use a value only if `available_at_utc` < decision time. The dbt test `no_feature_after_decision_time` enforces this. Never disable or weaken it.
5. **Point-in-time reference data.** VN30 membership as of each date. Bank financials enter on `published_at`; model features use the first-released version, never later restatements.
6. **Price-limit checks** compare against the exchange reference price, not the previous close, using the limits in force on each date (`dbt/seeds/`, Paper 1 D-003).
   - Today: ±7% HOSE, ±10% HNX, ±15% UPCoM.
   - Earlier: HOSE ±5% and HNX ±7% before 2013-01-15; UPCoM ±10% before 2015-07-01.
   - Use `prices_daily_limits`. Where `limit_status != 'computed'` (UPCoM, and HNX before 2013-07-29, used VWAP references), the limit is unknown and is never guessed.
7. **External libraries are wrapped** in our own client modules under `src/vnbank/ingestion/`. Pin versions. yfinance: always pass `auto_adjust=False`, store raw prices and compute adjustments ourselves.
8. **Vietnamese holidays** (e.g. Tết): global features use the cumulative return since the last Vietnamese session.
9. **Adjusted prices are for returns and scale-free ratios only.** `prices_daily_adjusted` is back-adjusted, so every price level is rescaled by corporate actions that happen *later*. Returns, ATR20 / price and other ratios are unaffected. Anything that depends on a price level (tick size, price bands, low-price filters, reference prices) must use `prices_daily_raw`.

## vnstock (Vietnamese market data)

- **Generation 6 only:** `vnstock==6.0.1` and `vnstock-oapi==0.1.2`, installed in the project environment by uv from the explicit `vnstock` index in `pyproject.toml`. Never `pip install`, never `~/.venv`, never older generations (`vnstock` ≤5, `vnstock3`, `vnstock_data`, `vnai`); those stopped working on 2026-11-10.
- **Currently unused.** Daily prices come from CafeF's bulk archives (ADR 0002, `src/vnbank/ingestion/market/cafef_client.py`). If vnstock is used later: every call names its source explicitly (no default), and calls go only through `src/vnbank/ingestion/market/vnstock_client.py`.
- **Keys:** the user stores them in their own terminal (`uv run vnstock login`, `uv run vnstock keys set <source>`, or the git-ignored `.env`). Never ask for a key in chat, never put one in code, files or output, never print variables that hold keys, never open `.env`. Check with `uv run vnstock keys` or `uv run vnstock doctor`.
- **Releases expire** (6.0.1 runs until 2027-11-16) and can be disabled remotely. Save every response to the raw layer with the vnstock version, source and `vnstock.cite(df)`. Research reads only frozen snapshots, never re-downloads.
- **Licence:** the Community edition is for personal, study and research use. Serving vnstock-sourced data to third parties (a public API or MCP server) needs a written agreement with Vnstock; rights to the data itself follow each source's terms.
- Look functions up with `uv run vnstock tools` and `uv run vnstock doc <Class.group.method>` instead of guessing. vnstock's trading skills (signals, portfolios) are out of scope here.

## Research rules

- **The design lives in `research/paper1/configs/main.yaml`**, read through `vnbank.research.shared.config.load(1)`. Code reads parameters from config, never hard-coded values; `tests/unit/research/test_config.py` pins Paper 1's pre-registered values. Do not change the main design to improve results. If a change seems warranted, propose it and log it in `research/paper1/DECISIONS.md` before running it.
- **Models read only a frozen snapshot** (`data/snapshots/<hash>/`, hash recorded in `research/snapshots.md`), never live tables. Each run records which snapshot it used.
- **Log every run** in `research/paper1/runs/<timestamp>-<name>/`, indexed in `RUNS.md`: config, snapshot hash, git commit (taken at the start of the run; `+dirty` if uncommitted), metrics. Report all runs, not just the best.
- **If a result looks too good, stop and run the `leakage-audit` skill** before reporting it.
- **Every number in a paper is generated by code.** `vnbank.research.shared` writes tables and `\newcommand` macros to `papers/paper1/generated/`. Never type a result by hand.
- **Never invent a citation.** Every reference must be checked (the DOI resolves, and authors, year and title match). Mark anything unverified with `\todo{verify}`.
- The paper uses LaTeX: `main.tex` follows the journal's (Wiley) template, which is not redistributed (`scripts/setup-wiley-template.sh`); `preprint.tex` is a plain layout. APA references (`apacite`); the appendix is a separate `supplement.tex`. Compile with `tectonic -X compile <file>.tex`. Use the `research-paper-writing` skill when drafting and the `paper-review` skill before anything goes to the supervisor.

## Paper 1 rules (trend reversals)

- **Pre-specified main design:** directional-change threshold θ = 2 × ATR20 / price (trailing only), main horizon 5 trading days, decision time 09:00. Robustness: k = 1.5 and 3, decision at HOSE close.
- **Chronological splits only.** Walk-forward with an expanding window from 2012, refit each January, test years 2017–2026 (2026 is partial, ending 2026-11-20). Purge training rows whose swing ends inside the test window; 20-trading-day embargo. Never use random or shuffled splits. Fit scalers, imputers and feature selection inside the training window only.
- **Test years are touched only by the final walk-forward run.** Tuning uses purged inner CV within the training window. Development work stays inside 2012–2016 (D-012).
- **Sanity checks:** Kaplan–Meier baseline; shuffled-label control (C-index ≈ 0.5). Red flags: daily direction accuracy above ~60%, R² on daily returns above a few percent, a C-index far above the baseline.
- **Baselines (D-016):** H1 is tested against Kaplan–Meier. Predictability beyond the label mechanics is claimed only against the mechanical baseline (swing age + `swing_dist`).
- **Metrics:** Uno's C-index, IPCW integrated Brier score, calibration at 5/10/20 days, time-dependent AUC, block-bootstrap confidence intervals. Trading test: long-only, T+2 settlement, no fill at limit-down, 0.4% round-trip cost (0.2% and 0.8% sensitivity), deflated Sharpe ratio.

## Working style

- Before multi-file changes, write a short plan and wait for approval.
- Work on feature branches, merge to `main` via PR. Commit messages: `feat:`, `fix:`, `data:`, `research:`, `paper:`, `docs:`; mention the paper where relevant (e.g. `research(paper1): …`).
- Tests are required for every ingestion client, every dbt model (dbt tests), and the swing labeller (pytest with hand-built price series whose reversals are known).
- Say why before adding a dependency.
- Ask before: deleting data, changing a pre-specified design, or starting a job expected to take more than an hour.
