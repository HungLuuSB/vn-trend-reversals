"""Development model comparison (research/DECISIONS.md D-014), inside 2012-2016 only.

    uv run python -m research.dev_compare --features-run <research/runs/...-features-...>

Per outer fold (2014, 2015, 2016; expanding training, purge, embargo, validation censored at
2016-12-31): nested tuning on the last training year by integrated Brier score, refit, then
Uno C / IBS / td-AUC / calibration for KM, logistic hazard, gradient-boosted hazard, Cox and
random survival forest; the A-C vs A-D ablation (RQ2); the shuffled-label control; paired
moving-block bootstrap intervals per fold and pooled.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from research.eval.bootstrap import paired_ci
from research.eval.metrics import calibration, ibs, surv, td_auc, uno_c
from research.features.assemble import BLOCKS
from research.models.zoo import GRIDS, make_model
from research.run_meta import code_version
from research.walkforward import DEV_END, DEV_FOLDS, TAU, TOO_GOOD_C, split

REPO = Path(__file__).resolve().parents[1]
TIMES = np.arange(1, 21)
HORIZONS = np.array([5, 10, 20])
MODELS = ["km", "logit", "gbm", "cox", "rsf"]


def tune(name, features, inner_train, inner_val, log) -> dict:
    if len(GRIDS[name]) == 1:
        return GRIDS[name][0]
    ytr, yva = surv(inner_train.event, inner_train.duration), surv(inner_val.event,
                                                                   inner_val.duration)  # fmt: skip
    scores = []
    for params in GRIDS[name]:
        s = make_model(name, features, **params).fit(inner_train).survival(inner_val, TIMES)
        scores.append(ibs(ytr, yva, s, TIMES))
        log(f"    tune {name} {params}: inner IBS {scores[-1]:.4f}")
    return GRIDS[name][int(np.argmin(scores))]


def metrics(y_train, val, s) -> dict:
    yva = surv(val.event, val.duration)
    risk = 1 - s[:, TAU - 1]
    return {
        "uno_c": uno_c(y_train, yva, risk, TAU),
        "ibs": ibs(y_train, yva, s, TIMES),
        "td_auc": dict(
            zip(
                map(str, HORIZONS),
                td_auc(y_train, yva, 1 - s[:, HORIZONS - 1], HORIZONS).round(4).tolist(),
                strict=True,
            )
        ),  # fmt: skip
        "calibration_5d": calibration(1 - s[:, 4], val.event.to_numpy(), val.duration.to_numpy(), 5)
        .round(4)
        .to_dict("list"),  # fmt: skip
    }


def bootstrap(y_train, val, preds: dict[str, np.ndarray], n: int, seed: int) -> dict:
    ev, du = val.event.to_numpy(), val.duration.to_numpy()

    def c_of(name):
        return lambda i: uno_c(y_train, surv(ev[i], du[i]), 1 - preds[name][i, TAU - 1], TAU)

    def b_of(name):
        return lambda i: ibs(y_train, surv(ev[i], du[i]), preds[name][i], TIMES)

    stats = {}
    for m in preds:
        stats[f"{m}:uno_c"] = c_of(m)
        stats[f"{m}:ibs"] = b_of(m)
    for m in preds:
        if m != "km":
            stats[f"{m}-km:ibs"] = lambda i, m=m: b_of(m)(i) - b_of("km")(i)
    if "logit_ABC" in preds:
        stats["ABCD-ABC:uno_c"] = lambda i: c_of("logit")(i) - c_of("logit_ABC")(i)
        stats["ABCD-ABC:ibs"] = lambda i: b_of("logit")(i) - b_of("logit_ABC")(i)
    return paired_ci(val.trade_date.to_numpy(), stats, block=20, n=n, seed=seed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--features-run", required=True)
    parser.add_argument("--bootstrap", type=int, default=200)
    parser.add_argument("--shuffle-seeds", type=int, default=10)
    parser.add_argument("--models", default=",".join(MODELS))
    args = parser.parse_args(argv)
    models = args.models.split(",")

    commit = code_version()  # at the start: the code this run actually executes
    fr = Path(args.features_run)
    ds = pd.read_parquet(fr / "dataset.parquet")
    fcfg = json.loads((fr / "config.json").read_text())
    snap = REPO / "research" / "snapshots" / fcfg["snapshot_id"]
    sessions = np.sort(pd.to_datetime(
        pd.read_parquet(snap / "sessions_hose.parquet").trade_date).to_numpy())  # fmt: skip
    ds = ds[ds.trade_date <= DEV_END]
    feats = {"ABCD": [c for b in "ABCD" for c in BLOCKS[b]],
             "ABC": [c for b in "ABC" for c in BLOCKS[b]]}  # fmt: skip

    run = REPO / "research" / "runs" / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-devcompare"
    run.mkdir(parents=True)
    logf = open(run / "log.txt", "w")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    results, pooled_preds, pooled_val = {}, {}, []
    last_y_train = None
    for year in DEV_FOLDS:
        t0 = time.time()
        train, val = split(ds, sessions, year, dev=True)
        inner_train, inner_val = split(train, sessions, year - 1, dev=False)
        log(f"{year}: train {len(train):,} (inner {len(inner_train):,} / {len(inner_val):,}) "
            f"val {len(val):,}")  # fmt: skip
        y_train = surv(train.event, train.duration)
        preds, fold = {}, {"chosen": {}, "metrics": {}}
        for name in models:
            params = tune(name, feats["ABCD"], inner_train, inner_val, log)
            fold["chosen"][name] = params
            preds[name] = make_model(name, feats["ABCD"], **params).fit(train).survival(val, TIMES)
            fold["metrics"][name] = metrics(y_train, val, preds[name])
            log(f"  {name} {params}: C {fold['metrics'][name]['uno_c']:.3f} "
                f"IBS {fold['metrics'][name]['ibs']:.4f}")  # fmt: skip
        if "logit" in models:
            p_abc = tune("logit", feats["ABC"], inner_train, inner_val, log)
            fold["chosen"]["logit_ABC"] = p_abc
            preds["logit_ABC"] = make_model("logit", feats["ABC"], **p_abc).fit(train).survival(
                val, TIMES)  # fmt: skip
            fold["metrics"]["logit_ABC"] = metrics(y_train, val, preds["logit_ABC"])
            log(f"  logit_ABC {p_abc}: C {fold['metrics']['logit_ABC']['uno_c']:.3f} "
                f"IBS {fold['metrics']['logit_ABC']['ibs']:.4f}")  # fmt: skip
            cs = []
            for seed in range(args.shuffle_seeds):
                perm = np.random.default_rng(seed).permutation(len(train))
                shuf = train.copy()
                shuf["duration"] = train.duration.to_numpy()[perm]
                shuf["event"] = train.event.to_numpy()[perm]
                s = make_model("logit", feats["ABCD"], **fold["chosen"]["logit"], seed=seed).fit(
                    shuf).survival(val, np.array([TAU]))  # fmt: skip
                cs.append(uno_c(y_train, surv(val.event, val.duration), 1 - s[:, 0], TAU))
            fold["shuffled_uno_c"] = {
                "values": np.round(cs, 4).tolist(),
                "mean": float(np.mean(cs)),
                "sd": float(np.std(cs, ddof=1)),
            }
            log(f"  shuffled C mean {np.mean(cs):.3f} sd {np.std(cs, ddof=1):.3f}")
        fold["bootstrap"] = bootstrap(y_train, val, preds, args.bootstrap, seed=year)
        results[str(year)] = fold
        for k, v in preds.items():
            pooled_preds.setdefault(k, []).append(v)
        pooled_val.append(val)
        last_y_train = y_train
        log(f"  fold done in {time.time() - t0:.0f}s")

    pv = pd.concat(pooled_val, ignore_index=True)
    pp = {k: np.vstack(v) for k, v in pooled_preds.items()}
    results["pooled"] = {
        "metrics": {k: metrics(last_y_train, pv, v) for k, v in pp.items()},
        "bootstrap": bootstrap(last_y_train, pv, pp, args.bootstrap, seed=0),
    }

    warnings = []
    for y in map(str, DEV_FOLDS):
        f = results[y]
        for name, m in f["metrics"].items():
            if m["uno_c"] > TOO_GOOD_C:
                warnings.append(f"{y} {name}: C {m['uno_c']:.3f} > {TOO_GOOD_C}: STOP, run the "
                                "leakage-audit skill")  # fmt: skip
        if "shuffled_uno_c" in f:
            sm = f["shuffled_uno_c"]
            if abs(sm["mean"] - 0.5) > max(0.02, 3 * sm["sd"] / np.sqrt(len(sm["values"]))):
                warnings.append(f"{y}: mean shuffled C {sm['mean']:.3f} is not ~0.5")
    cfg = {"protocol": "D-014", "features_run": fr.name, "snapshot_id": fcfg["snapshot_id"],
           "git_commit": commit, "models": models, "grids": {m: GRIDS[m] for m in models},
           "folds": DEV_FOLDS, "bootstrap": args.bootstrap, "block": 20,
           "shuffle_seeds": args.shuffle_seeds}  # fmt: skip
    (run / "config.json").write_text(json.dumps(cfg, indent=2))
    (run / "metrics.json").write_text(json.dumps({"results": results, "warnings": warnings},
                                                 indent=2, default=float))  # fmt: skip
    log(json.dumps({"run_dir": str(run), "warnings": warnings}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
