"""Descriptive SHAP values for the evaluated 2026 models (FINAL_RUN_PROTOCOL.md 5e, D-026).

    uv run python -m vnbank.research.survival.final.shap_explain

Explains the two models the final run saved for this purpose (cache/main/2026/models/:
gbm_ABCD and nn_seq_ABCD) on a fixed random sample of 5,000 rows of the 2026 test year. The
explained output is the model's probability that the swing reverses within the main horizon
(5 sessions), 1 - S(5 | x). Explanation only: no test, no tuning, nothing feeds back into any
result.

Method: permutation SHAP (shap.PermutationExplainer) over the 38 static features of
specification ABCD, with an independent masker whose background is a fixed random sample of
the 2026 training rows. For the sequence neural model, each row's own 60-session price sequence
is held at its value, so the attributions are for the static features given the sequence.

Writes research/paper1/runs/<UTC timestamp>-final-shap/: config.json, metrics.json (mean
|SHAP| and the direction of each feature, block shares, additivity check) and shap_*.parquet
(git-ignored).
"""

from __future__ import annotations

import json
import pickle
import sys
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from vnbank.common import paths
from vnbank.research.shared.run_meta import code_version
from vnbank.research.survival.features.sequence import add_sequences
from vnbank.research.survival.final import specs as S
from vnbank.research.survival.walkforward import split

YEAR = 2026
N_ROWS = 5000  # protocol 5e
N_BACKGROUND = 100
MAX_EVALS = 401  # about five antithetic permutations per row
SEED = 20261127
WORKERS = 8  # processes; each uses one thread (set OMP_NUM_THREADS=1 when running)
CACHE = paths.REPO / "data" / "final_cache" / "vnbank" / "cache" / "main" / str(YEAR)
FEATURES_RUN = "20261126T052338Z-features-1f0c80b50427479e-k2"
BLOCKS = {
    "A": ["swing_dir", "swing_age", "log_age", "swing_age_conf", "swing_move", "swing_dist",
          "theta"],
    "B": ["ret_1", "ret_5", "ret_20", "atr_pct", "rsi_14", "vol_rel_20", "limit_up_hits_5",
          "limit_down_hits_5", "limit_known_5", "close_at_limit"],
    "C": ["vnindex_ret", "vn30_ret", "advance_share", "matched_value_rel_20", "idx_swing_dir",
          "idx_swing_age", "idx_swing_dist"],
    "D": ["spx_ret", "nasdaq_ret", "vix_chg", "vix_level", "ust10_chg", "dxy_ret", "gold_ret",
          "brent_ret", "hsi_ret", "sse_ret", "usdvnd_ret", "usdcny_ret", "gpr_level", "gpr_chg"],
}  # fmt: skip


def risk(model, X: pd.DataFrame) -> np.ndarray:
    """Probability of a confirmed reversal within the main horizon."""
    return 1.0 - model.survival(X, np.array([5]))[:, 0]


def explain(model, rows: pd.DataFrame, background: pd.DataFrame, feats: list[str],
            seq_cols: list[str] | None, log=print) -> tuple[np.ndarray, np.ndarray]:  # fmt: skip
    """SHAP values (rows x feats) and base values. With seq_cols, each row keeps its own
    sequence while its static features are masked."""
    import shap

    masker = shap.maskers.Independent(background[feats].to_numpy(dtype="float64"),
                                      max_samples=N_BACKGROUND)  # fmt: skip
    values = np.zeros((len(rows), len(feats)))
    base = np.zeros(len(rows))
    if seq_cols is None:

        def f(z):
            return risk(model, pd.DataFrame(z, columns=feats))

        ex = shap.PermutationExplainer(f, masker, seed=SEED)
        out = ex(rows[feats].to_numpy(dtype="float64"), max_evals=MAX_EVALS, silent=True)
        return out.values, out.base_values  # noqa: PD011 (shap Explanation)
    for i in range(len(rows)):
        seq = rows[seq_cols].iloc[i].to_numpy(dtype="float32")

        def f(z, seq=seq):
            X = pd.DataFrame(z, columns=feats)
            S_ = pd.DataFrame(np.repeat(seq[None, :], len(z), axis=0), columns=seq_cols)
            return risk(model, pd.concat([X, S_], axis=1))

        ex = shap.PermutationExplainer(f, masker, seed=SEED)
        o = ex(rows[feats].iloc[[i]].to_numpy(dtype="float64"), max_evals=MAX_EVALS,
               silent=True)  # fmt: skip
        values[i], base[i] = o.values[0], np.ravel(o.base_values)[0]  # noqa: PD011
        if (i + 1) % 500 == 0:
            log(f"  nn_seq_ABCD: {i + 1}/{len(rows)}")
    return values, base


def _chunk(args):
    """Worker: explain one chunk of rows (models are reloaded in each process)."""
    import torch

    torch.set_num_threads(1)
    name, rows, bg, feats, seq_cols = args
    model = pickle.loads((CACHE / "models" / f"{name}.pkl").read_bytes())
    return explain(model, rows, bg, feats, seq_cols, log=lambda m: None)


def explain_parallel(name, rows, bg, feats, seq_cols, workers: int):
    from concurrent.futures import ProcessPoolExecutor

    parts = np.array_split(np.arange(len(rows)), workers * 4)
    jobs = [(name, rows.iloc[p], bg, feats, seq_cols) for p in parts if len(p)]
    with ProcessPoolExecutor(workers) as ex:
        res = list(ex.map(_chunk, jobs))
    return np.vstack([r[0] for r in res]), np.concatenate([np.ravel(r[1]) for r in res])


def summarise(values: np.ndarray, base: np.ndarray, X: pd.DataFrame, pred: np.ndarray,
              feats: list[str]) -> dict:  # fmt: skip
    mean_abs = np.abs(values).mean(axis=0)
    direction = {}
    for j, c in enumerate(feats):
        x = X[c].to_numpy(dtype="float64")
        ok = ~np.isnan(x)
        if ok.sum() > 2 and np.std(x[ok]) > 0 and np.std(values[ok, j]) > 0:
            direction[c] = float(np.corrcoef(x[ok], values[ok, j])[0, 1])
        else:
            direction[c] = None
    total = mean_abs.sum()
    blocks = {b: float(sum(mean_abs[feats.index(c)] for c in cs) / total)
              for b, cs in BLOCKS.items()}  # fmt: skip
    return {
        "mean_abs_shap": dict(zip(feats, mean_abs.tolist(), strict=True)),
        "direction_corr": direction,
        "block_share": blocks,
        "mean_prediction": float(pred.mean()),
        "mean_base_value": float(np.mean(base)),
        "additivity_max_abs_error": float(np.max(np.abs(base + values.sum(axis=1) - pred))),
    }


def main(argv: list[str] | None = None) -> int:
    commit = code_version()
    if commit.endswith("+dirty"):
        raise SystemExit("working tree is dirty: reported results come from committed code")
    fr = paths.runs_dir(1) / FEATURES_RUN
    fcfg = json.loads((fr / "config.json").read_text())
    snap = paths.SNAPSHOTS / fcfg["snapshot_id"]
    sessions = np.sort(pd.to_datetime(
        pd.read_parquet(snap / "sessions_hose.parquet").trade_date).to_numpy())  # fmt: skip
    ds = pd.read_parquet(fr / "dataset.parquet")
    ds["trade_date"] = pd.to_datetime(ds.trade_date)
    ds["end_date"] = pd.to_datetime(ds.end_date)
    train, test = split(ds, sessions, YEAR, dev=False)
    rng = np.random.default_rng(SEED)
    rows = test.iloc[np.sort(rng.choice(len(test), size=min(N_ROWS, len(test)), replace=False))]
    bg = train.iloc[np.sort(rng.choice(len(train), size=N_BACKGROUND, replace=False))]
    cols = ["ticker", "trade_date", "open_adj", "high_adj", "low_adj", "close_adj", "volume"]
    prices = pd.read_parquet(snap / "prices_adjusted.parquet", columns=cols)
    prices["trade_date"] = pd.to_datetime(prices.trade_date)
    rows = add_sequences(rows.reset_index(drop=True), prices)
    seq_cols = [c for c in rows.columns if c.startswith("seq_")]
    feats = list(S.ABCD)

    out = paths.runs_dir(1) / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-final-shap"
    out.mkdir(parents=True)
    cfg = {"git_commit": commit, "created_at_utc": datetime.now(UTC).isoformat(),
           "protocol": "FINAL_RUN_PROTOCOL.md 5e", "year": YEAR, "rows": len(rows),
           "background_rows": N_BACKGROUND, "max_evals": MAX_EVALS, "seed": SEED,
           "features_run": FEATURES_RUN, "snapshot_id": fcfg["snapshot_id"],
           "models": ["gbm_ABCD", "nn_seq_ABCD"], "output": "1 - S(5 | x)"}  # fmt: skip
    (out / "config.json").write_text(json.dumps(cfg, indent=1))
    metrics = {}
    for name, seq in (("gbm_ABCD", None), ("nn_seq_ABCD", seq_cols)):
        model = pickle.loads((CACHE / "models" / f"{name}.pkl").read_bytes())
        print(f"{name}: explaining {len(rows)} rows", flush=True)
        values, base = explain_parallel(name, rows, bg, feats, seq, WORKERS)
        pred = risk(model, rows[feats + (seq or [])])
        metrics[name] = summarise(values, base, rows, pred, feats)
        pd.DataFrame(values, columns=feats).assign(base=base, pred=pred).to_parquet(
            out / f"shap_{name}.parquet", index=False)  # fmt: skip
        (out / "metrics.json").write_text(json.dumps(metrics, indent=1))
    print(out.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
