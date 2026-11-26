"""Final run, one test year (FINAL_RUN_PROTOCOL.md, D-026): tune, refit and predict every
specification, and cache the predictions. Years are independent, so each can run on its own
machine. This step computes NO metric: the pooled evaluation (``final.evaluate``) reads the
caches and applies the stop rules before any result is shown.

    uv run python -m vnbank.research.survival.final.year --features-run <dir> --year 2017 \
        --out <cache dir> --final --i-confirm-final-run

Per year it writes <out>/<year>/:
  keys.parquet        test rows (ticker, trade_date, outcome, slicing flags)
  bank_keys.parquet   bank test rows (block E specs)
  preds/<spec>.npy    survival S(1..20) per spec on its test rows (float32); shuffled:<spec>
                      holds the permutations' 20-day risks; written as each spec finishes
  bank_preds/*.npy    the same for the block E specs on bank rows
  train_y.npz, bank_train_y.npz   training outcomes (IPCW in the evaluation)
  models/*.pkl        2026 only: the fitted gbm_ABCD and nn_seq_ABCD (SHAP, 5e)
  inner_p5.parquet    5-day reversal probabilities on the inner year (D-021 tau tuning)
  meta.json           chosen hyperparameters, shuffled-control risks, ABCDx coefficients,
                      timings, machine, code version, inputs
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from vnbank.common import paths
from vnbank.research.shared.config import load
from vnbank.research.shared.run_meta import code_version
from vnbank.research.survival.dev_compare import tune
from vnbank.research.survival.features.assemble import (
    add_bank_interactions,
    add_direction_interactions,
)
from vnbank.research.survival.features.block_e import add_block_e
from vnbank.research.survival.features.sequence import add_sequences
from vnbank.research.survival.final import specs as S
from vnbank.research.survival.models.zoo import make_model
from vnbank.research.survival.walkforward import EMBARGO_SESSIONS, IBS_TIMES, split

CFG = load(1)
TEST_YEARS = tuple(CFG["walkforward"]["test_years"])
STUDY_END = pd.Timestamp(CFG["study"]["end"])
H = CFG["evaluation"]["main_horizon"]
OUTER_EXTRA = {"nn": {"seeds": CFG["neural"]["outer_seeds"]}}  # D-022
KEY_COLS = ["ticker", "trade_date", "event", "duration", "end_date", "is_bank", "in_vn30",
            "close_at_limit", "limit_known_5", "swing_dir", "swing_age", "swing_dist"]  # fmt: skip


def prepare(ds: pd.DataFrame, prices: pd.DataFrame | None) -> pd.DataFrame:
    """Every derived column any final specification uses (interactions, foreign-flow
    indicator, 60-day sequences). Rows after the study end never exist (snapshot)."""
    if (pd.to_datetime(ds.trade_date) > STUDY_END).any():
        raise SystemExit("dataset has rows after the study end")
    if (pd.to_datetime(ds.end_date) > STUDY_END).any():
        raise SystemExit("dataset has labels ending after the study end")
    ds = add_bank_interactions(add_direction_interactions(ds))
    ds["foreign_missing"] = ds.foreign_net_share.isna().astype("float64")
    if prices is not None:
        ds = add_sequences(ds.reset_index(drop=True), prices)
    return ds.reset_index(drop=True)


def censored_split(ds: pd.DataFrame, sessions: np.ndarray, year: int):
    """D-025 sensitivity: training rows whose swing ends on/after the fold start are censored
    at the boundary (event 0, duration = sessions from t to the last session before it)
    instead of dropped. Embargo and the test rows are as in `split`."""
    start = pd.Timestamp(f"{year}-01-01")
    k = np.searchsorted(sessions, start.to_datetime64())
    embargo_start = sessions[max(0, k - EMBARGO_SESSIONS)]
    train = ds[ds.trade_date < embargo_start].copy()
    late = (train.end_date >= start).to_numpy()
    to_boundary = k - 1 - np.searchsorted(sessions, train.trade_date.to_numpy())
    train.loc[late, "event"] = 0
    train.loc[late, "duration"] = np.minimum(train.duration.to_numpy(), to_boundary)[late]
    _, test = split(ds, sessions, year, dev=False)
    return train, test


def _model(mname, feats, params, train, seed=None):
    kw = {**params, **({"seed": seed} if seed is not None else {})}
    return make_model(mname, feats, **kw).fit(train)


def _fit_predict(mname, feats, params, train, rows, seed=None):
    m = _model(mname, feats, params, train, seed)
    return m.survival(rows, IBS_TIMES).astype("float32")


class Cache:
    """Per-year cache written incrementally: one .npy per prediction set, saved atomically as
    soon as it exists, and meta.json after every step. A restarted (or --only) run skips what
    is already there and merges the rest, so a crash loses at most the step in progress."""

    def __init__(self, out: Path):
        self.out = out
        for d in ("preds", "bank_preds", "models"):
            (out / d).mkdir(parents=True, exist_ok=True)
        mp = out / "meta.json"
        self.meta = json.loads(mp.read_text()) if mp.exists() else {}
        for k in ("chosen", "seconds"):
            self.meta.setdefault(k, {})

    def has(self, kind: str, name: str) -> bool:
        return (self.out / kind / f"{name}.npy").exists()

    def put(self, kind: str, name: str, arr: np.ndarray) -> None:
        tmp = self.out / kind / f".{name}.tmp.npy"
        np.save(tmp, arr)
        tmp.replace(self.out / kind / f"{name}.npy")
        self.save()

    def save(self) -> None:
        tmp = self.out / ".meta.tmp.json"
        tmp.write_text(json.dumps(self.meta, indent=1, default=str))
        tmp.replace(self.out / "meta.json")


def load_preds(out: Path, kind: str = "preds") -> dict[str, np.ndarray]:
    d = Path(out) / kind
    return {f.stem: np.load(f) for f in sorted(d.glob("*.npy")) if not f.name.startswith(".")}


PERSIST = ("gbm_ABCD", "nn_seq_ABCD")  # D-026 5e: SHAP explains the evaluated 2026 models


def machine() -> dict:
    """Recorded at the start of a year (protocol section 7)."""
    import importlib.metadata as md

    info = {"host": platform.node(), "platform": platform.platform(), "cpus": os.cpu_count(),
            "python": platform.python_version()}  # fmt: skip
    for pkg in ("numpy", "pandas", "scikit-learn", "scikit-survival", "torch"):
        try:
            info[pkg] = md.version(pkg)
        except md.PackageNotFoundError:
            info[pkg] = None
    try:
        mem = Path("/proc/meminfo").read_text().splitlines()[0]
        info["mem_total"] = mem.split(":", 1)[1].strip()
        cpu = [x for x in Path("/proc/cpuinfo").read_text().splitlines() if "model name" in x]
        info["cpu_model"] = cpu[0].split(":", 1)[1].strip() if cpu else None
    except OSError:
        pass
    info["threads_env"] = {k: os.environ.get(k) for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS")}
    return info


def run_year(ds, sessions, year: int, out: Path, bank_sets: dict | None = None,
             only: set[str] | None = None, confirm: bool = False, log=print) -> dict:  # fmt: skip
    """Fit and cache one test year. `bank_sets`: block E variant -> bank-row dataset.
    `only`: restrict to these spec names (tests, partial reruns); results merge into the
    existing cache."""
    if year in TEST_YEARS and not confirm:
        raise SystemExit(f"{year} is a test year: the final run needs explicit confirmation")
    out = Path(out) / str(year)
    c = Cache(out)
    meta = c.meta
    meta["year"] = year
    meta.setdefault("machine_at_start", machine())
    want = lambda n: only is None or n in only  # noqa: E731
    quiet = lambda m: None  # noqa: E731  # tuning scores are not logged (no metric output)

    train, test = split(ds, sessions, year, dev=False)
    inner_train, inner_val = split(train, sessions, year - 1, dev=False)
    test[KEY_COLS].reset_index(drop=True).to_parquet(out / "keys.parquet", index=False)
    np.savez_compressed(out / "train_y.npz", duration=train.duration.to_numpy(),
                        event=train.event.to_numpy())  # IPCW in the evaluation  # fmt: skip
    meta["n"] = {"train": len(train), "test": len(test), "inner_train": len(inner_train),
                 "inner_val": len(inner_val)}  # fmt: skip
    log(f"{year}: train {len(train):,} inner {len(inner_train):,}/{len(inner_val):,} "
        f"test {len(test):,}")  # fmt: skip

    c.put("preds", "km", _fit_predict("km", [], {}, train, test))
    for name, (mname, feats, rows) in S.SPECS.items():
        if rows != "all" or not want(name) or (c.has("preds", name) and name in meta["chosen"]):
            continue
        t0 = time.time()
        params = tune(mname, feats, inner_train, inner_val, quiet)
        meta["chosen"][name] = params
        m = _model(mname, feats, {**params, **OUTER_EXTRA.get(mname, {})}, train)
        if name in PERSIST and year == TEST_YEARS[-1]:
            import pickle

            (out / "models" / f"{name}.pkl").write_bytes(pickle.dumps(m))
        meta["seconds"][name] = round(time.time() - t0, 1)
        c.put("preds", name, m.survival(test, IBS_TIMES).astype("float32"))
        log(f"  {name}: {params} ({meta['seconds'][name]}s)")

    if "ABCDx" in meta["chosen"]:
        p = meta["chosen"]["ABCDx"]
        if "abcdx_coef_std" not in meta:
            m = _model("logit", S.ABCDx, p, train)
            coef = m.m.model[-1].coef_[0][: len(S.ABCDx)]
            meta["abcdx_coef_std"] = dict(zip(S.ABCDx, np.round(coef, 6).tolist(), strict=True))
            c.save()
        for name, feats in S.LOO.items():  # D-018: no re-tuning
            if want(f"loo{name}") and not c.has("preds", f"loo{name}"):
                c.put("preds", f"loo{name}", _fit_predict("logit", feats, p, train, test))
        log("  ABCDx coefficients and D-018 variants done")

    for name, n_perm in S.SHUFFLED.items():  # outcome pairs permuted across training rows
        if name not in meta["chosen"] or c.has("preds", f"shuffled:{name}"):
            continue
        mname, feats, _ = S.SPECS[name]
        risks = []
        for k in range(n_perm):
            perm = np.random.default_rng(k).permutation(len(train))
            shuf = train.copy()
            shuf["duration"] = train.duration.to_numpy()[perm]
            shuf["event"] = train.event.to_numpy()[perm]
            s = _fit_predict(mname, feats, meta["chosen"][name], shuf, test, seed=k)
            risks.append(1 - s[:, -1])
        c.put("preds", f"shuffled:{name}", np.vstack(risks).T.astype("float32"))
        log(f"  shuffled {name}: {n_perm} permutations")

    if only is None or any(f"boundary:{b}" in only for b in S.BOUNDARY):  # D-025
        ctrain, _ = censored_split(ds, sessions, year)
        cinner_train, cinner_val = censored_split(ctrain, sessions, year - 1)
        c.put("preds", "boundary:km", _fit_predict("km", [], {}, ctrain, test))
        for name in S.BOUNDARY:
            key = f"boundary:{name}"
            if c.has("preds", key) and key in meta["chosen"]:
                continue
            mname, feats, _ = S.SPECS[name]
            meta["chosen"][key] = tune(mname, feats, cinner_train, cinner_val, quiet)
            c.put("preds", key, _fit_predict(mname, feats, meta["chosen"][key], ctrain, test))
        meta["n"]["boundary_train"] = len(ctrain)
        log("  boundary-censoring sensitivity done")

    ipath = out / "inner_p5.parquet"  # D-021: tau on the inner year
    inner_rows = ds[ds.trade_date.dt.year == year - 1]
    ip = (
        pd.read_parquet(ipath)
        if ipath.exists()
        else pd.DataFrame(
            {"ticker": inner_rows.ticker.to_numpy(), "trade_date": inner_rows.trade_date.to_numpy()}
        )
    )
    for name in S.BACKTEST:
        if name in meta["chosen"] and f"p5:{name}" not in ip:
            mname, feats, _ = S.SPECS[name]
            s = _fit_predict(mname, feats, meta["chosen"][name], inner_train, inner_rows)
            ip[f"p5:{name}"] = 1 - s[:, H - 1]
            ip.to_parquet(ipath, index=False)

    main_bank = None
    for variant, bank in (bank_sets or {}).items():
        btrain, btest = split(bank, sessions, year, dev=False)
        binner_train, binner_val = split(btrain, sessions, year - 1, dev=False)
        bkeys = btest[["ticker", "trade_date"]].reset_index(drop=True)
        if variant is None:
            main_bank = bkeys
            btest[KEY_COLS].reset_index(drop=True).to_parquet(out / "bank_keys.parquet",
                                                               index=False)  # fmt: skip
            np.savez_compressed(out / "bank_train_y.npz", duration=btrain.duration.to_numpy(),
                                event=btrain.event.to_numpy())  # fmt: skip
            c.put("bank_preds", "bank_km", _fit_predict("km", [], {}, btrain, btest))
            names = [n for n, v in S.SPECS.items() if v[2] == "bank"]
        else:
            if main_bank is not None and not bkeys.equals(main_bank):
                raise SystemExit(f"block E variant {variant}: bank test rows differ from main")
            names = list(S.E_VARIANT_SPECS)
        for name in names:
            key = name if variant is None else f"{name}@{variant}"
            if not want(name) or (c.has("bank_preds", key) and key in meta["chosen"]):
                continue
            mname, feats, _ = S.SPECS[name]
            meta["chosen"][key] = tune(mname, feats, binner_train, binner_val, quiet)
            c.put("bank_preds", key, _fit_predict(mname, feats, meta["chosen"][key], btrain,
                                                  btest))  # fmt: skip
        log(f"  block E {variant or 'main'} done")

    lock = paths.REPO / "uv.lock"
    if lock.exists():
        import hashlib

        meta["uv_lock_sha256"] = hashlib.sha256(lock.read_bytes()).hexdigest()
    meta["machine_at_end"] = machine()
    c.save()
    return meta


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI wiring
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--features-run", required=True)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--i-confirm-final-run", action="store_true")
    ap.add_argument(
        "--only",
        default=None,
        help="comma-separated spec names (robustness runs, e.g. k = 1.5 / 3)",
    )
    a = ap.parse_args(argv)
    only = set(a.only.split(",")) if a.only else None
    if not (a.final and a.i_confirm_final_run):
        raise SystemExit("the final run needs --final --i-confirm-final-run (D-026)")
    if a.year not in TEST_YEARS:
        raise SystemExit(f"{a.year} is not a test year (labels of other years are not censored "
                         "at the development end); use the dev runners")  # fmt: skip
    commit = code_version()
    if commit.endswith("+dirty"):
        raise SystemExit("working tree is dirty: the final run uses committed code only")
    fr = Path(a.features_run)
    fcfg = json.loads((fr / "config.json").read_text())
    snap_id = fcfg["snapshot_id"]
    snap = paths.SNAPSHOTS / snap_id
    for need in ("block_e_npl.parquet", "news_counts.parquet"):
        if not (snap / need).exists():
            raise SystemExit(f"snapshot {snap_id} lacks {need}: freeze it first (D-024)")
    sessions = np.sort(pd.to_datetime(
        pd.read_parquet(snap / "sessions_hose.parquet").trade_date).to_numpy())  # fmt: skip
    cols = ["ticker", "trade_date", "open_adj", "high_adj", "low_adj", "close_adj", "volume"]
    prices = pd.read_parquet(snap / "prices_adjusted.parquet", columns=cols)
    prices["trade_date"] = pd.to_datetime(prices.trade_date)
    import hashlib

    ds_sha = hashlib.sha256((fr / "dataset.parquet").read_bytes()).hexdigest()
    manifest = json.loads((snap / "manifest.json").read_text())
    ds = pd.read_parquet(fr / "dataset.parquet")
    ds["trade_date"] = pd.to_datetime(ds.trade_date)
    ds["end_date"] = pd.to_datetime(ds.end_date)
    ds = prepare(ds, prices)
    bank_sets, bank_meta = {}, {}
    variants = (None, *S.E_VARIANTS)
    if only is not None and not any(S.SPECS.get(n, ("", [], ""))[2] == "bank" for n in only):
        variants = ()  # no block E spec requested
    for variant in variants:
        bank_sets[variant], bank_meta[str(variant)] = add_block_e(
            ds, snapshot=snap_id, variant=variant, sessions=sessions)  # fmt: skip
    a.out.mkdir(parents=True, exist_ok=True)
    logf = open(a.out / f"log_{a.year}.txt", "w")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    ident = {"git_commit": commit, "features_run": fr.name, "snapshot_id": snap_id,
             "snapshot_manifest_id": manifest.get("snapshot_id"), "dataset_sha256": ds_sha,
             "k": fcfg.get("k")}  # fmt: skip
    prev = a.out / str(a.year) / "meta.json"
    if prev.exists():  # a merge into an existing cache must be the same run
        old = json.loads(prev.read_text())
        for k, v in ident.items():
            if old.get(k) not in (None, v):
                raise SystemExit(f"cache {a.year} was written with {k}={old[k]}, now {v}")
    t0 = time.time()
    meta = run_year(ds, sessions, a.year, a.out, bank_sets=bank_sets, only=only, confirm=True,
                    log=log)  # fmt: skip
    runs = meta.setdefault("invocations", [])
    runs.append({"git_commit": commit, "only": sorted(only) if only else None,
                 "wall_seconds": round(time.time() - t0)})  # fmt: skip
    meta.update(ident)
    meta["block_e_inputs"] = bank_meta or meta.get("block_e_inputs")
    meta["wall_seconds"] = sum(r["wall_seconds"] for r in runs)
    (a.out / str(a.year) / "meta.json").write_text(json.dumps(meta, indent=1, default=str))
    log(f"{a.year} done in {meta['wall_seconds']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
