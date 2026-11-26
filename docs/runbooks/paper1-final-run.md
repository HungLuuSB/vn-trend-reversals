# Runbook: Paper 1 final run (D-026)

The single run that touches the test years 2017–2026. Do each step in order and log it in `research/paper1/runs/RUNS.md`. Nothing here may start before the user's explicit go-ahead (CLAUDE.md, D-024).

## 0. Gates (all must be done)

- [ ] The final-run code is merged after its independent leakage review (D-025).
- [ ] The vast.ai account is ready. **The user** creates the instances: no API key ever enters this repo or the chat.
- [ ] The referee-style design review (D-024 gate 4) is done.
- [ ] A full `dbt build` passes: `cd dbt && uv run --env-file ../.env dbt build`, with no `--select`. The snapshot gate checks this.
- [ ] The working tree is clean and on `main`.

## 1. Freeze (laptop)

```bash
uv run python -m vnbank.research.shared.snapshot --label final
```

- The freeze freezes the warehouse tables plus block E, news counts and the Paper 2 inputs (`paper2/`), and drops rows after 2026-11-20.
- It records the id in `research/snapshots.md`.
- Check `manifest.json` → `derived_rows_dropped_after_study_end`.

## 2. Labels and features from the frozen snapshot (laptop)

```bash
SNAP=<id>
uv run python -m vnbank.research.swings.build --snapshot $SNAP            # k = 2, 1.5, 3
for k in 2 1.5 3; do
  uv run python -m vnbank.research.survival.features.assemble --snapshot $SNAP \
      --labels-run research/paper1/runs/<labels run> --k $k
done
```

## 3. The user's go-ahead

Show the user the gates, the snapshot id and the commit. Wait for an explicit "go".

## 4. vast.ai: one test year per instance

**Package once on the laptop.** No `.env`, no untracked files, no Paper 2 data:

```bash
git bundle create /tmp/vnbank-final.bundle HEAD   # a real repo: the commit is recorded, .env is not in it
tar czf /tmp/snap.tar.gz -C data/snapshots --exclude="$SNAP/paper2" $SNAP
tar czf /tmp/features.tar.gz -C research/paper1/runs <features k2> <features k1_5> <features k3>
```

**On each instance (CPU, ≥ 8 cores, ≥ 32 GB RAM):**

```bash
git clone vnbank-final.bundle vnbank && cd vnbank && git log -1 --oneline
mkdir -p data/snapshots research/paper1/runs
tar xzf ../snap.tar.gz -C data/snapshots && tar xzf ../features.tar.gz -C research/paper1/runs
pip install uv && uv sync --frozen
Y=2017   # one year per instance
uv run python -m vnbank.research.survival.final.year --features-run research/paper1/runs/<k2> \
    --year $Y --out cache/main --final --i-confirm-final-run
for K in k1_5 k3; do
  uv run python -m vnbank.research.survival.final.year --features-run research/paper1/runs/<$K> \
      --year $Y --out cache/$K --only M,ABCDx --final --i-confirm-final-run
done
nproc; free -g; lscpu | head -20 > cache/machine_$Y.txt
```

- The bundle carries the commit, so `code_version()` records it, and the dirty check still guards the run.
- **Before the real years,** run `uv run pytest tests/unit/research/final` on one instance. This checks the environment: `uv sync --frozen` must resolve every locked package, including the explicit `vnstock` index, without credentials.
- **Copy back:** `cache/` (predictions, keys, `meta.json`, logs) to the laptop under `data/final_cache/`, which git ignores.
- **Destroy the instance.** Record the instance type and its hourly price in `RUNS.md`.

## 5. Evaluation (laptop)

```bash
uv run python -m vnbank.research.survival.final.evaluate --cache data/final_cache/main \
    --final --i-confirm-final-run
```

- If it exits with `STOP.json`, run the `leakage-audit` skill. Read nothing else.
- **Budget.** The evaluation computes Uno's C on about 99k rows (about 18 s per call) for every model across 3 × 200 resamples, which comes to several hours on 8 cores. Ask the user before starting it, or run it on a vast.ai instance as well.
- Otherwise (`EVAL` = that run's folder):

```bash
uv run python -m vnbank.research.survival.final.backtest --cache data/final_cache/main \
    --snapshot $SNAP --evaluate-run $EVAL --final --i-confirm-final-run
for K in 1.5 3; do  # robustness: evaluate each k cache first, then its trading test
  T=k${K/./_}
  uv run python -m vnbank.research.survival.final.evaluate --cache data/final_cache/$T \
      --label $T --final --i-confirm-final-run
  uv run python -m vnbank.research.survival.final.backtest --cache data/final_cache/$T \
      --snapshot $SNAP --k $K --evaluate-run <that run> --final --i-confirm-final-run
done
uv run python -m vnbank.research.survival.final.rq4 --features-run research/paper1/runs/<k2> \
    --evaluate-run $EVAL --final --i-confirm-final-run
```

- **Afterwards:**
  - SHAP on the saved 2026 models (`data/final_cache/main/2026/models/`);
  - the Abolmakarem appendix on development data.

## 6. After

- Log every run (and any crash or stop) in `RUNS.md`.
- Register the runs in the paper-number registry, then generate the macros and tables.
- No test-year result is used to change anything in the protocol. Anything added later is labelled post hoc.
