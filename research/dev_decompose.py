"""Nested feature-set comparisons (research/DECISIONS.md D-015, D-016).

    uv run python -m research.dev_decompose --features-run <...> [--protocol D-016]

Development only (inside 2012-2016, folds 2014/15/16, same protocol as D-014). The tuned
logistic hazard is fitted on nested feature sets AGE < A < AB < ABC and compared with KM and
with each other (paired moving-block bootstrap).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from research.dev_compare import HORIZONS, TIMES, metrics, tune
from research.eval.bootstrap import paired_ci
from research.eval.metrics import ibs, surv, td_auc, uno_c
from research.features.assemble import BLOCKS, FEATURES_MECH
from research.models.zoo import make_model
from research.walkforward import DEV_END, DEV_FOLDS, TAU, TOO_GOOD_C, split

REPO = Path(__file__).resolve().parents[1]
SPECS = {
    "AGE": ["swing_age", "log_age"],
    "A": list(BLOCKS["A"]),
    "AB": [*BLOCKS["A"], *BLOCKS["B"]],
    "ABC": [*BLOCKS["A"], *BLOCKS["B"], *BLOCKS["C"]],
}
DIFFS = [("A", "AGE"), ("AB", "A"), ("ABC", "AB"), ("ABC", "AGE")]

# D-016: incremental value over the mechanical baseline M (swing age + swing_dist)
SPECS_D016 = {
    "M": list(FEATURES_MECH),
    "MB": [*FEATURES_MECH, *BLOCKS["B"]],
    "MBC": [*FEATURES_MECH, *BLOCKS["B"], *BLOCKS["C"]],
    "MD": [*FEATURES_MECH, *BLOCKS["D"]],
    "ABC": [*BLOCKS["A"], *BLOCKS["B"], *BLOCKS["C"]],
    "ABCD": [*BLOCKS["A"], *BLOCKS["B"], *BLOCKS["C"], *BLOCKS["D"]],
}
DIFFS_D016 = [("ABC", "M"), ("MB", "M"), ("MBC", "MB"), ("MD", "M"), ("ABCD", "ABC")]
PROTOCOLS = {"D-015": (SPECS, DIFFS), "D-016": (SPECS_D016, DIFFS_D016)}


def boot(y_train, val, preds: dict[str, np.ndarray], n: int, seed: int, diffs=DIFFS) -> dict:
    ev, du = val.event.to_numpy(), val.duration.to_numpy()

    def c(m):
        return lambda i: uno_c(y_train, surv(ev[i], du[i]), 1 - preds[m][i, TAU - 1], TAU)

    def b(m):
        return lambda i: ibs(y_train, surv(ev[i], du[i]), preds[m][i], TIMES)

    def a5(m):
        return lambda i: float(td_auc(y_train, surv(ev[i], du[i]), 1 - preds[m][i, 4:5],
                                      np.array([5]))[0])  # fmt: skip

    stats = {}
    for m in preds:
        stats[f"{m}:uno_c"], stats[f"{m}:ibs"], stats[f"{m}:auc5"] = c(m), b(m), a5(m)
    for hi, lo in diffs:
        for key, f in (("uno_c", c), ("ibs", b), ("auc5", a5)):
            stats[f"{hi}-{lo}:{key}"] = lambda i, f=f, hi=hi, lo=lo: f(hi)(i) - f(lo)(i)
    return paired_ci(val.trade_date.to_numpy(), stats, block=20, n=n, seed=seed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--features-run", required=True)
    parser.add_argument("--bootstrap", type=int, default=200)
    parser.add_argument("--protocol", choices=sorted(PROTOCOLS), default="D-015")
    args = parser.parse_args(argv)
    specs, diffs = PROTOCOLS[args.protocol]

    fr = Path(args.features_run)
    ds = pd.read_parquet(fr / "dataset.parquet")
    fcfg = json.loads((fr / "config.json").read_text())
    snap = REPO / "research" / "snapshots" / fcfg["snapshot_id"]
    sessions = np.sort(pd.to_datetime(
        pd.read_parquet(snap / "sessions_hose.parquet").trade_date).to_numpy())  # fmt: skip
    ds = ds[ds.trade_date <= DEV_END]

    run = (
        REPO
        / "research"
        / "runs"
        / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-devdecompose-{args.protocol}"
    )
    run.mkdir(parents=True)
    logf = open(run / "log.txt", "w")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    results, pooled_preds, pooled_val, last_y_train = {}, {}, [], None
    for year in DEV_FOLDS:
        t0 = time.time()
        train, val = split(ds, sessions, year, dev=True)
        inner_train, inner_val = split(train, sessions, year - 1, dev=False)
        log(f"{year}: train {len(train):,} val {len(val):,}")
        y_train = surv(train.event, train.duration)
        preds, fold = {}, {"chosen": {}, "metrics": {}}
        preds["km"] = make_model("km", []).fit(train).survival(val, TIMES)
        fold["metrics"]["km"] = metrics(y_train, val, preds["km"])
        for spec, feats in specs.items():
            params = tune("logit", feats, inner_train, inner_val, log)
            fold["chosen"][spec] = params
            preds[spec] = make_model("logit", feats, **params).fit(train).survival(val, TIMES)
            fold["metrics"][spec] = metrics(y_train, val, preds[spec])
            m = fold["metrics"][spec]
            log(f"  {spec} {params}: C {m['uno_c']:.3f} IBS {m['ibs']:.4f} td-AUC {m['td_auc']}")
        fold["bootstrap"] = boot(y_train, val, preds, args.bootstrap, seed=year, diffs=diffs)
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
        "bootstrap": boot(last_y_train, pv, pp, args.bootstrap, seed=0, diffs=diffs),
    }

    pm = results["pooled"]["metrics"]
    if args.protocol == "D-015":  # interpretation rule (pooled, 5-day td-AUC)
        age, full = pm["AGE"]["td_auc"]["5"] - 0.5, pm["ABC"]["td_auc"]["5"] - 0.5
        results["age_share_auc5"] = age / full if full > 0 else float("nan")
        results["mainly_age_effect"] = bool(full > 0 and age >= 0.8 * full)
    else:  # D-016: beyond the label mechanics only if both pooled intervals exclude zero
        b = results["pooled"]["bootstrap"]
        results["beats_mechanical"] = bool(b["ABC-M:uno_c"]["lo"] > 0 and b["ABC-M:ibs"]["hi"] < 0)

    warnings = [f"{y} {s}: C {m['uno_c']:.3f} > {TOO_GOOD_C}: STOP, run the leakage-audit skill"
                for y in map(str, DEV_FOLDS) for s, m in results[y]["metrics"].items()
                if m["uno_c"] > TOO_GOOD_C]  # fmt: skip
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                            text=True, check=True).stdout.strip()  # fmt: skip
    cfg = {"protocol": args.protocol, "features_run": fr.name, "snapshot_id": fcfg["snapshot_id"],
           "git_commit": commit, "specs": specs, "diffs": diffs, "folds": DEV_FOLDS,
           "horizons": HORIZONS.tolist(), "bootstrap": args.bootstrap, "block": 20}  # fmt: skip
    (run / "config.json").write_text(json.dumps(cfg, indent=2))
    (run / "metrics.json").write_text(json.dumps({"results": results, "warnings": warnings},
                                                 indent=2, default=float))  # fmt: skip
    log(
        json.dumps(
            {
                "run_dir": str(run),
                "age_share_auc5": results["age_share_auc5"],
                "mainly_age_effect": results["mainly_age_effect"],
                "warnings": warnings,
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
